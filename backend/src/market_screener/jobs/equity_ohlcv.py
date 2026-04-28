"""Equity OHLCV ingestion job."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    EquityAdapterFactory,
    build_finnhub_equity_adapter_factory,
)
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    PriceNormalizationError,
    normalize_finnhub_stock_candles,
    persist_normalized_prices,
)
from market_screener.providers.finnhub import FinnhubClient

logger = logging.getLogger("market_screener.jobs.equity_ohlcv")


class EquityOhlcvParseError(ValueError):
    """Raised when provider OHLCV payload is invalid."""


CandlePoint = NormalizedPricePoint


@dataclass(frozen=True)
class EquityOhlcvIngestionResult:
    """Outcome summary for one equity OHLCV ingestion run."""

    processed_symbols: int
    ingested_rows: int
    skipped_rows: int
    failed_symbols: int
    no_data_symbols: int
    market_closed_symbols: int = 0
    idempotent_skip: bool = False


def normalize_finnhub_candles(payload: dict[str, Any]) -> list[CandlePoint]:
    """Normalize Finnhub candle payload to canonical price-point schema."""

    try:
        return normalize_finnhub_stock_candles(payload)
    except PriceNormalizationError as exc:
        raise EquityOhlcvParseError(str(exc)) from exc


class EquityOhlcvIngestionJob:
    """Fetch and persist OHLCV candles for active equity assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        finnhub_client_factory: Callable[[], FinnhubClient],
        *,
        resolution: str,
        lookback_days: int,
        failure_store: IngestionFailureStore | None = None,
        dead_letter_store: DeadLetterStore | None = None,
        trading_calendar: TradingCalendar | None = None,
        symbol_allowlist: set[str] | None = None,
        adapter_factory: EquityAdapterFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._resolution = resolution
        self._lookback_days = lookback_days
        self._failure_store = failure_store
        self._dead_letter_store = dead_letter_store
        self._trading_calendar = trading_calendar or TradingCalendar()
        self._symbol_allowlist = (
            {symbol.upper() for symbol in symbol_allowlist} if symbol_allowlist else None
        )
        self._adapter_factory = adapter_factory or build_finnhub_equity_adapter_factory(
            finnhub_client_factory
        )

    def run(self, *, now_utc: datetime | None = None) -> EquityOhlcvIngestionResult:
        now_utc = now_utc or datetime.now(UTC)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=UTC)
        from_unix = int((now_utc - timedelta(days=self._lookback_days)).timestamp())
        to_unix = int(now_utc.timestamp())
        window_anchor = now_utc.date().isoformat()
        ingest_id = uuid4().hex

        with self._session_factory() as session:
            query = select(Asset).where(Asset.asset_type == "equity", Asset.active.is_(True))
            if self._symbol_allowlist:
                query = query.where(Asset.symbol.in_(sorted(self._symbol_allowlist)))
            assets = session.scalars(query).all()

        ingested_rows = 0
        skipped_rows = 0
        failed_symbols = 0
        no_data_symbols = 0
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
                    candles = adapter.fetch_candles(
                        asset.symbol,
                        resolution=self._resolution,
                        from_unix=from_unix,
                        to_unix=to_unix,
                    )
                except AdapterNormalizationError as exc:
                    logger.warning(
                        "equity_ohlcv_symbol_dead_lettered",
                        extra={
                            "symbol": asset.symbol,
                            "provider": "finnhub",
                            "error": str(exc),
                        },
                    )
                    if self._dead_letter_store is not None:
                        dead_letter_key = build_idempotency_key(
                            "dead_letter",
                            {
                                "job_name": "equity_ohlcv_ingestion",
                                "symbol": asset.symbol,
                                "provider": "finnhub",
                                "payload_type": "ohlcv_candles",
                                "reason": "normalization_error",
                                "error": str(exc),
                            },
                        )
                        self._dead_letter_store.record_dead_letter(
                            dead_letter_key=dead_letter_key,
                            job_name="equity_ohlcv_ingestion",
                            asset_symbol=asset.symbol,
                            provider_name="finnhub",
                            payload_type="ohlcv_candles",
                            reason="normalization_error",
                            error_message=str(exc),
                            payload=exc.payload,
                            context={
                                "symbol": asset.symbol,
                                "provider": "finnhub",
                                "resolution": self._resolution,
                                "lookback_days": self._lookback_days,
                                "window_anchor": window_anchor,
                                "from_unix": from_unix,
                                "to_unix": to_unix,
                            },
                        )
                    failed_symbols += 1
                    continue
                except Exception as exc:
                    logger.exception(
                        "equity_ohlcv_symbol_failed",
                        extra={"symbol": asset.symbol, "error": str(exc)},
                    )
                    if self._failure_store is not None:
                        self._failure_store.record_failure(
                            failure_key=build_idempotency_key(
                                "equity_ohlcv_failure",
                                {
                                    "symbol": asset.symbol,
                                    "provider": "finnhub",
                                    "resolution": self._resolution,
                                    "lookback_days": self._lookback_days,
                                    "window_anchor": window_anchor,
                                },
                            ),
                            job_name="equity_ohlcv_ingestion",
                            asset_symbol=asset.symbol,
                            provider_name="finnhub",
                            error_message=str(exc),
                            context={
                                "symbol": asset.symbol,
                                "provider": "finnhub",
                                "resolution": self._resolution,
                                "lookback_days": self._lookback_days,
                                "window_anchor": window_anchor,
                                "from_unix": from_unix,
                                "to_unix": to_unix,
                            },
                        )
                    failed_symbols += 1
                    continue

                if not candles:
                    no_data_symbols += 1
                    continue

                newly_ingested, newly_skipped = _persist_candles_for_asset(
                    self._session_factory,
                    asset_id=asset.id,
                    source="finnhub",
                    ingest_id=ingest_id,
                    candles=candles,
                )
                ingested_rows += newly_ingested
                skipped_rows += newly_skipped

        return EquityOhlcvIngestionResult(
            processed_symbols=len(assets),
            ingested_rows=ingested_rows,
            skipped_rows=skipped_rows,
            failed_symbols=failed_symbols,
            no_data_symbols=no_data_symbols,
            market_closed_symbols=market_closed_symbols,
        )


def run_equity_ohlcv_ingestion(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> EquityOhlcvIngestionResult:
    """Run equity OHLCV ingestion with default runtime wiring."""

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
    symbol_fingerprint = _active_equity_symbol_fingerprint(resolved_session_factory)
    window_anchor = reference_now.date().isoformat()
    idempotency_key = build_idempotency_key(
        "equity_ohlcv_ingestion",
        {
            "resolution": resolved_settings.equity_ohlcv_resolution,
            "lookback_days": resolved_settings.equity_ohlcv_lookback_days,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("equity_ohlcv_ingestion", idempotency_key):
        return EquityOhlcvIngestionResult(
            processed_symbols=0,
            ingested_rows=0,
            skipped_rows=0,
            failed_symbols=0,
            no_data_symbols=0,
            market_closed_symbols=0,
            idempotent_skip=True,
        )

    def _client_factory() -> FinnhubClient:
        return FinnhubClient.from_settings(resolved_settings)

    job = EquityOhlcvIngestionJob(
        resolved_session_factory,
        _client_factory,
        resolution=resolved_settings.equity_ohlcv_resolution,
        lookback_days=resolved_settings.equity_ohlcv_lookback_days,
        failure_store=failure_store,
        dead_letter_store=dead_letter_store,
        trading_calendar=trading_calendar,
    )
    with resolved_audit.track_job_run(
        "equity_ohlcv_ingestion",
        details={
            "provider": "finnhub",
            "resolution": resolved_settings.equity_ohlcv_resolution,
            "lookback_days": resolved_settings.equity_ohlcv_lookback_days,
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
                "market_closed_symbols": result.market_closed_symbols,
                "idempotent_skip": False,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for manual equity OHLCV ingestion runs."""

    result = run_equity_ohlcv_ingestion()
    logger.info(
        "equity_ohlcv_ingestion_completed",
        extra={
            "processed_symbols": result.processed_symbols,
            "ingested_rows": result.ingested_rows,
            "skipped_rows": result.skipped_rows,
            "failed_symbols": result.failed_symbols,
            "no_data_symbols": result.no_data_symbols,
            "market_closed_symbols": result.market_closed_symbols,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "equity_ohlcv_ingestion:"
        f" processed_symbols={result.processed_symbols}"
        f" ingested_rows={result.ingested_rows}"
        f" skipped_rows={result.skipped_rows}"
        f" failed_symbols={result.failed_symbols}"
        f" no_data_symbols={result.no_data_symbols}"
        f" market_closed_symbols={result.market_closed_symbols}"
        f" idempotent_skip={result.idempotent_skip}"
    )


def _active_equity_symbol_fingerprint(session_factory: SessionFactory) -> str:
    symbols: list[str]
    with session_factory() as session:
        symbols = sorted(
            session.scalars(
                select(Asset.symbol).where(Asset.asset_type == "equity", Asset.active.is_(True))
            ).all()
        )

    if not symbols:
        return "none"
    return "|".join(symbols)


def _persist_candles_for_asset(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    source: str,
    ingest_id: str,
    candles: list[CandlePoint],
) -> tuple[int, int]:
    """Persist candles for one asset, skipping rows that already exist."""
    return persist_normalized_prices(
        session_factory,
        asset_id=asset_id,
        source=source,
        ingest_id=ingest_id,
        points=candles,
    )


if __name__ == "__main__":
    main()
