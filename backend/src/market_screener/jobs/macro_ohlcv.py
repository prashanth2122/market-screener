"""Forex and commodity OHLCV ingestion job."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from market_screener.core.trading_calendar import TradingCalendar
from market_screener.core.settings import Settings, get_settings
from market_screener.db.models.core import Asset
from market_screener.db.session import (
    SessionFactory,
    create_session_factory_from_settings,
)
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.dead_letters import DeadLetterStore
from market_screener.jobs.idempotency import build_idempotency_key
from market_screener.jobs.ingestion_adapters import (
    AdapterNormalizationError,
    MacroAdapterFactory,
    MacroIngestionAdapter,
    build_alpha_vantage_macro_adapter_factory,
)
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    PriceNormalizationError,
    normalize_alpha_vantage_commodity_daily as normalize_alpha_vantage_commodity_daily_shared,
    normalize_alpha_vantage_fx_daily as normalize_alpha_vantage_fx_daily_shared,
    persist_normalized_prices,
)
from market_screener.providers.alpha_vantage import AlphaVantageClient

logger = logging.getLogger("market_screener.jobs.macro_ohlcv")


class MacroOhlcvParseError(ValueError):
    """Raised when provider OHLCV payload is invalid."""


MacroCandlePoint = NormalizedPricePoint


@dataclass(frozen=True)
class MacroOhlcvIngestionResult:
    """Outcome summary for one forex/commodity OHLCV ingestion run."""

    processed_symbols: int
    ingested_rows: int
    skipped_rows: int
    failed_symbols: int
    no_data_symbols: int
    unsupported_symbols: int
    market_closed_symbols: int = 0
    idempotent_skip: bool = False


def normalize_alpha_vantage_fx_daily(payload: dict[str, Any]) -> list[MacroCandlePoint]:
    """Normalize Alpha Vantage FX_DAILY payload to canonical price-point schema."""

    try:
        return normalize_alpha_vantage_fx_daily_shared(payload)
    except PriceNormalizationError as exc:
        raise MacroOhlcvParseError(str(exc)) from exc


def normalize_alpha_vantage_commodity_daily(payload: dict[str, Any]) -> list[MacroCandlePoint]:
    """Normalize Alpha Vantage commodity payload to canonical price-point schema."""

    try:
        return normalize_alpha_vantage_commodity_daily_shared(payload)
    except PriceNormalizationError as exc:
        raise MacroOhlcvParseError(str(exc)) from exc


class MacroOhlcvIngestionJob:
    """Fetch and persist OHLC data for active forex and commodity assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        alpha_vantage_client_factory: Callable[[], AlphaVantageClient],
        *,
        lookback_days: int,
        forex_outputsize: str,
        commodity_interval: str,
        failure_store: IngestionFailureStore | None = None,
        dead_letter_store: DeadLetterStore | None = None,
        trading_calendar: TradingCalendar | None = None,
        symbol_allowlist: set[str] | None = None,
        adapter_factory: MacroAdapterFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._lookback_days = lookback_days
        self._forex_outputsize = forex_outputsize
        self._commodity_interval = commodity_interval
        self._failure_store = failure_store
        self._dead_letter_store = dead_letter_store
        self._trading_calendar = trading_calendar or TradingCalendar()
        self._symbol_allowlist = (
            {symbol.upper() for symbol in symbol_allowlist} if symbol_allowlist else None
        )
        self._adapter_factory = adapter_factory or build_alpha_vantage_macro_adapter_factory(
            alpha_vantage_client_factory
        )

    def run(self, *, now_utc: datetime | None = None) -> MacroOhlcvIngestionResult:
        now_utc = now_utc or datetime.now(UTC)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=UTC)
        window_anchor = now_utc.date().isoformat()
        window_start_date = (now_utc - timedelta(days=self._lookback_days)).date()
        ingest_id = uuid4().hex

        with self._session_factory() as session:
            query = select(Asset).where(
                Asset.asset_type.in_(("forex", "commodity")),
                Asset.active.is_(True),
            )
            if self._symbol_allowlist:
                query = query.where(Asset.symbol.in_(sorted(self._symbol_allowlist)))
            assets = session.scalars(query).all()

        ingested_rows = 0
        skipped_rows = 0
        failed_symbols = 0
        no_data_symbols = 0
        unsupported_symbols = 0
        market_closed_symbols = 0

        with self._adapter_factory() as adapter:
            for asset in assets:
                if not self._trading_calendar.is_market_open(
                    asset_type=asset.asset_type,
                    exchange=asset.exchange,
                    on_date=now_utc,
                ):
                    market_closed_symbols += 1
                    continue
                try:
                    candles = self._fetch_asset_candles(adapter, asset, window_start_date)
                except AdapterNormalizationError as exc:
                    payload_type = "fx_daily" if asset.asset_type == "forex" else "commodity_daily"
                    logger.warning(
                        "macro_ohlcv_symbol_dead_lettered",
                        extra={
                            "symbol": asset.symbol,
                            "asset_type": asset.asset_type,
                            "provider": "alpha_vantage",
                            "error": str(exc),
                        },
                    )
                    if self._dead_letter_store is not None:
                        dead_letter_key = build_idempotency_key(
                            "dead_letter",
                            {
                                "job_name": "macro_ohlcv_ingestion",
                                "symbol": asset.symbol,
                                "asset_type": asset.asset_type,
                                "provider": "alpha_vantage",
                                "payload_type": payload_type,
                                "reason": "normalization_error",
                                "error": str(exc),
                            },
                        )
                        self._dead_letter_store.record_dead_letter(
                            dead_letter_key=dead_letter_key,
                            job_name="macro_ohlcv_ingestion",
                            asset_symbol=asset.symbol,
                            provider_name="alpha_vantage",
                            payload_type=payload_type,
                            reason="normalization_error",
                            error_message=str(exc),
                            payload=exc.payload,
                            context={
                                "symbol": asset.symbol,
                                "asset_type": asset.asset_type,
                                "provider": "alpha_vantage",
                                "window_anchor": window_anchor,
                                "lookback_days": self._lookback_days,
                                "base_currency": asset.base_currency,
                                "quote_currency": asset.quote_currency,
                                "forex_outputsize": self._forex_outputsize,
                                "commodity_interval": self._commodity_interval,
                            },
                        )
                    failed_symbols += 1
                    continue
                except Exception as exc:
                    logger.exception(
                        "macro_ohlcv_symbol_failed",
                        extra={
                            "symbol": asset.symbol,
                            "asset_type": asset.asset_type,
                            "error": str(exc),
                        },
                    )
                    if self._failure_store is not None:
                        self._failure_store.record_failure(
                            failure_key=build_idempotency_key(
                                "macro_ohlcv_failure",
                                {
                                    "symbol": asset.symbol,
                                    "asset_type": asset.asset_type,
                                    "provider": "alpha_vantage",
                                    "window_anchor": window_anchor,
                                    "lookback_days": self._lookback_days,
                                },
                            ),
                            job_name="macro_ohlcv_ingestion",
                            asset_symbol=asset.symbol,
                            provider_name="alpha_vantage",
                            error_message=str(exc),
                            context={
                                "symbol": asset.symbol,
                                "asset_type": asset.asset_type,
                                "provider": "alpha_vantage",
                                "window_anchor": window_anchor,
                                "lookback_days": self._lookback_days,
                                "base_currency": asset.base_currency,
                                "quote_currency": asset.quote_currency,
                                "forex_outputsize": self._forex_outputsize,
                                "commodity_interval": self._commodity_interval,
                            },
                        )
                    failed_symbols += 1
                    continue

                if candles is None:
                    unsupported_symbols += 1
                    continue

                if not candles:
                    no_data_symbols += 1
                    continue

                newly_ingested, newly_skipped = _persist_macro_candles_for_asset(
                    self._session_factory,
                    asset_id=asset.id,
                    source="alpha_vantage",
                    ingest_id=ingest_id,
                    candles=candles,
                )
                ingested_rows += newly_ingested
                skipped_rows += newly_skipped

        return MacroOhlcvIngestionResult(
            processed_symbols=len(assets),
            ingested_rows=ingested_rows,
            skipped_rows=skipped_rows,
            failed_symbols=failed_symbols,
            no_data_symbols=no_data_symbols,
            unsupported_symbols=unsupported_symbols,
            market_closed_symbols=market_closed_symbols,
        )

    def _fetch_asset_candles(
        self,
        adapter: MacroIngestionAdapter,
        asset: Asset,
        window_start_date: date,
    ) -> list[MacroCandlePoint] | None:
        points = adapter.fetch_candles(
            asset,
            forex_outputsize=self._forex_outputsize,
            commodity_interval=self._commodity_interval,
            window_start_date=window_start_date,
        )
        return points


def run_macro_ohlcv_ingestion(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> MacroOhlcvIngestionResult:
    """Run forex/commodity OHLCV ingestion with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = now_utc or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    failure_store = IngestionFailureStore(
        resolved_session_factory,
        max_attempts=resolved_settings.ingestion_failure_max_attempts,
        retry_backoff_minutes=resolved_settings.ingestion_failure_retry_backoff_minutes,
    )
    dead_letter_store = DeadLetterStore(resolved_session_factory)
    trading_calendar = TradingCalendar.from_settings(resolved_settings)
    symbol_fingerprint = _active_macro_symbol_fingerprint(resolved_session_factory)
    window_anchor = reference_now.date().isoformat()
    idempotency_key = build_idempotency_key(
        "macro_ohlcv_ingestion",
        {
            "lookback_days": resolved_settings.macro_ohlcv_lookback_days,
            "forex_outputsize": resolved_settings.macro_ohlcv_forex_outputsize,
            "commodity_interval": resolved_settings.macro_ohlcv_commodity_interval,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("macro_ohlcv_ingestion", idempotency_key):
        return MacroOhlcvIngestionResult(
            processed_symbols=0,
            ingested_rows=0,
            skipped_rows=0,
            failed_symbols=0,
            no_data_symbols=0,
            unsupported_symbols=0,
            market_closed_symbols=0,
            idempotent_skip=True,
        )

    def _client_factory() -> AlphaVantageClient:
        return AlphaVantageClient.from_settings(resolved_settings)

    job = MacroOhlcvIngestionJob(
        resolved_session_factory,
        _client_factory,
        lookback_days=resolved_settings.macro_ohlcv_lookback_days,
        forex_outputsize=resolved_settings.macro_ohlcv_forex_outputsize,
        commodity_interval=resolved_settings.macro_ohlcv_commodity_interval,
        failure_store=failure_store,
        dead_letter_store=dead_letter_store,
        trading_calendar=trading_calendar,
    )
    with resolved_audit.track_job_run(
        "macro_ohlcv_ingestion",
        details={
            "provider": "alpha_vantage",
            "lookback_days": resolved_settings.macro_ohlcv_lookback_days,
            "forex_outputsize": resolved_settings.macro_ohlcv_forex_outputsize,
            "commodity_interval": resolved_settings.macro_ohlcv_commodity_interval,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
            "idempotency_key": idempotency_key,
            "idempotency_hit": False,
        },
        idempotency_key=idempotency_key,
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "processed_symbols": result.processed_symbols,
                "ingested_rows": result.ingested_rows,
                "skipped_rows": result.skipped_rows,
                "failed_symbols": result.failed_symbols,
                "no_data_symbols": result.no_data_symbols,
                "unsupported_symbols": result.unsupported_symbols,
                "market_closed_symbols": result.market_closed_symbols,
                "idempotent_skip": False,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for manual forex/commodity OHLCV ingestion runs."""

    result = run_macro_ohlcv_ingestion()
    logger.info(
        "macro_ohlcv_ingestion_completed",
        extra={
            "processed_symbols": result.processed_symbols,
            "ingested_rows": result.ingested_rows,
            "skipped_rows": result.skipped_rows,
            "failed_symbols": result.failed_symbols,
            "no_data_symbols": result.no_data_symbols,
            "unsupported_symbols": result.unsupported_symbols,
            "market_closed_symbols": result.market_closed_symbols,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "macro_ohlcv_ingestion:"
        f" processed_symbols={result.processed_symbols}"
        f" ingested_rows={result.ingested_rows}"
        f" skipped_rows={result.skipped_rows}"
        f" failed_symbols={result.failed_symbols}"
        f" no_data_symbols={result.no_data_symbols}"
        f" unsupported_symbols={result.unsupported_symbols}"
        f" market_closed_symbols={result.market_closed_symbols}"
        f" idempotent_skip={result.idempotent_skip}"
    )


def _active_macro_symbol_fingerprint(session_factory: SessionFactory) -> str:
    rows: list[tuple[str, str, str | None, str]]
    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    Asset.symbol,
                    Asset.asset_type,
                    Asset.base_currency,
                    Asset.quote_currency,
                )
                .where(
                    Asset.asset_type.in_(("forex", "commodity")),
                    Asset.active.is_(True),
                )
                .order_by(Asset.symbol.asc())
            )
        )

    if not rows:
        return "none"
    parts = [
        f"{symbol}:{asset_type}:{base_currency or ''}:{quote_currency}"
        for symbol, asset_type, base_currency, quote_currency in rows
    ]
    return "|".join(parts)


def _persist_macro_candles_for_asset(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    source: str,
    ingest_id: str,
    candles: list[MacroCandlePoint],
) -> tuple[int, int]:
    """Persist forex/commodity candles for one asset, skipping duplicates."""
    return persist_normalized_prices(
        session_factory,
        asset_id=asset_id,
        source=source,
        ingest_id=ingest_id,
        points=candles,
    )


if __name__ == "__main__":
    main()
