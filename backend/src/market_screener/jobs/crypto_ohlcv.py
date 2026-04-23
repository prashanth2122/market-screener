"""Crypto OHLCV ingestion job."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.db.models.core import Asset
from market_screener.db.session import (
    SessionFactory,
    create_session_factory_from_settings,
)
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key, file_sha256
from market_screener.jobs.ingestion_adapters import (
    AdapterSymbolMappingError,
    CryptoAdapterFactoryBuilder,
    build_coingecko_crypto_adapter_factory,
)
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    PriceNormalizationError,
    normalize_coingecko_ohlc as normalize_coingecko_ohlc_shared,
    persist_normalized_prices,
)
from market_screener.providers.coingecko import CoinGeckoClient

logger = logging.getLogger("market_screener.jobs.crypto_ohlcv")


class CryptoOhlcvParseError(ValueError):
    """Raised when provider OHLCV payload is invalid."""


class CryptoSymbolMapParseError(ValueError):
    """Raised when crypto symbol map cannot be loaded from universe file."""


CryptoCandlePoint = NormalizedPricePoint


@dataclass(frozen=True)
class CryptoOhlcvIngestionResult:
    """Outcome summary for one crypto OHLCV ingestion run."""

    processed_symbols: int
    ingested_rows: int
    skipped_rows: int
    failed_symbols: int
    no_data_symbols: int
    missing_mapping_symbols: int
    idempotent_skip: bool = False


def load_crypto_symbol_map(path: Path) -> dict[str, str]:
    """Load symbol->CoinGecko-id mapping from universe JSON file."""

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CryptoSymbolMapParseError(f"symbol_universe_file_missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CryptoSymbolMapParseError(f"symbol_universe_invalid_json: {path}") from exc

    if not isinstance(payload, dict):
        raise CryptoSymbolMapParseError("symbol_universe_payload_must_be_object")

    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise CryptoSymbolMapParseError("symbol_universe_symbols_must_be_array")

    symbol_map: dict[str, str] = {}
    for index, entry in enumerate(symbols):
        if not isinstance(entry, dict):
            raise CryptoSymbolMapParseError(f"symbol_entry_{index}_must_be_object")
        if str(entry.get("asset_type", "")).lower() != "crypto":
            continue

        symbol = entry.get("symbol")
        coingecko_id = entry.get("coingecko_id")
        if not isinstance(symbol, str) or not symbol.strip():
            raise CryptoSymbolMapParseError(f"symbol_entry_{index}_symbol_must_be_non_empty_string")
        if not isinstance(coingecko_id, str) or not coingecko_id.strip():
            raise CryptoSymbolMapParseError(
                f"symbol_entry_{index}_coingecko_id_must_be_non_empty_string"
            )

        symbol_map[symbol.strip().upper()] = coingecko_id.strip()

    return symbol_map


def normalize_coingecko_ohlc(payload: list[Any]) -> list[CryptoCandlePoint]:
    """Normalize CoinGecko OHLC payload to canonical price-point schema."""

    try:
        return normalize_coingecko_ohlc_shared(payload)
    except PriceNormalizationError as exc:
        raise CryptoOhlcvParseError(str(exc)) from exc


class CryptoOhlcvIngestionJob:
    """Fetch and persist OHLC candles for active crypto assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        coingecko_client_factory: Callable[[], CoinGeckoClient],
        *,
        symbol_map_path: Path,
        vs_currency: str,
        days: int,
        failure_store: IngestionFailureStore | None = None,
        symbol_allowlist: set[str] | None = None,
        adapter_factory_builder: CryptoAdapterFactoryBuilder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_map_path = symbol_map_path
        self._vs_currency = vs_currency
        self._days = days
        self._failure_store = failure_store
        self._symbol_allowlist = (
            {symbol.upper() for symbol in symbol_allowlist} if symbol_allowlist else None
        )
        self._adapter_factory_builder = (
            adapter_factory_builder
            or build_coingecko_crypto_adapter_factory(coingecko_client_factory)
        )

    def run(self, *, now_utc: datetime | None = None) -> CryptoOhlcvIngestionResult:
        now_utc = now_utc or datetime.now(UTC)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=UTC)
        window_anchor = now_utc.date().isoformat()
        ingest_id = uuid4().hex
        symbol_to_coin_id = load_crypto_symbol_map(self._symbol_map_path)

        with self._session_factory() as session:
            query = select(Asset).where(Asset.asset_type == "crypto", Asset.active.is_(True))
            if self._symbol_allowlist:
                query = query.where(Asset.symbol.in_(sorted(self._symbol_allowlist)))
            assets = session.scalars(query).all()

        ingested_rows = 0
        skipped_rows = 0
        failed_symbols = 0
        no_data_symbols = 0
        missing_mapping_symbols = 0

        with self._adapter_factory_builder(symbol_to_coin_id) as adapter:
            for asset in assets:
                coin_id = symbol_to_coin_id.get(asset.symbol.upper())
                try:
                    candles = adapter.fetch_candles(
                        asset.symbol,
                        vs_currency=self._vs_currency,
                        days=self._days,
                    )
                except AdapterSymbolMappingError:
                    missing_mapping_symbols += 1
                    continue
                except Exception as exc:
                    logger.exception(
                        "crypto_ohlcv_symbol_failed",
                        extra={
                            "symbol": asset.symbol,
                            "coin_id": coin_id,
                            "error": str(exc),
                        },
                    )
                    if self._failure_store is not None:
                        self._failure_store.record_failure(
                            failure_key=build_idempotency_key(
                                "crypto_ohlcv_failure",
                                {
                                    "symbol": asset.symbol,
                                    "coin_id": coin_id,
                                    "provider": "coingecko",
                                    "vs_currency": self._vs_currency,
                                    "days": self._days,
                                    "window_anchor": window_anchor,
                                },
                            ),
                            job_name="crypto_ohlcv_ingestion",
                            asset_symbol=asset.symbol,
                            provider_name="coingecko",
                            error_message=str(exc),
                            context={
                                "symbol": asset.symbol,
                                "coin_id": coin_id,
                                "provider": "coingecko",
                                "vs_currency": self._vs_currency,
                                "days": self._days,
                                "window_anchor": window_anchor,
                            },
                        )
                    failed_symbols += 1
                    continue

                if not candles:
                    no_data_symbols += 1
                    continue

                newly_ingested, newly_skipped = _persist_crypto_candles_for_asset(
                    self._session_factory,
                    asset_id=asset.id,
                    source="coingecko",
                    ingest_id=ingest_id,
                    candles=candles,
                )
                ingested_rows += newly_ingested
                skipped_rows += newly_skipped

        return CryptoOhlcvIngestionResult(
            processed_symbols=len(assets),
            ingested_rows=ingested_rows,
            skipped_rows=skipped_rows,
            failed_symbols=failed_symbols,
            no_data_symbols=no_data_symbols,
            missing_mapping_symbols=missing_mapping_symbols,
        )


def run_crypto_ohlcv_ingestion(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> CryptoOhlcvIngestionResult:
    """Run crypto OHLCV ingestion with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_path = Path(resolved_settings.symbol_universe_file)
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    failure_store = IngestionFailureStore(
        resolved_session_factory,
        max_attempts=resolved_settings.ingestion_failure_max_attempts,
        retry_backoff_minutes=resolved_settings.ingestion_failure_retry_backoff_minutes,
    )
    symbol_fingerprint = _active_crypto_symbol_fingerprint(resolved_session_factory)
    reference_now = now_utc or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    window_anchor = reference_now.date().isoformat()
    idempotency_key = build_idempotency_key(
        "crypto_ohlcv_ingestion",
        {
            "vs_currency": resolved_settings.crypto_ohlcv_vs_currency,
            "days": resolved_settings.crypto_ohlcv_days,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
            "universe_sha256": file_sha256(resolved_path),
        },
    )

    if resolved_audit.has_completed_run("crypto_ohlcv_ingestion", idempotency_key):
        return CryptoOhlcvIngestionResult(
            processed_symbols=0,
            ingested_rows=0,
            skipped_rows=0,
            failed_symbols=0,
            no_data_symbols=0,
            missing_mapping_symbols=0,
            idempotent_skip=True,
        )

    def _client_factory() -> CoinGeckoClient:
        return CoinGeckoClient.from_settings(resolved_settings)

    job = CryptoOhlcvIngestionJob(
        resolved_session_factory,
        _client_factory,
        symbol_map_path=resolved_path,
        vs_currency=resolved_settings.crypto_ohlcv_vs_currency,
        days=resolved_settings.crypto_ohlcv_days,
        failure_store=failure_store,
    )
    with resolved_audit.track_job_run(
        "crypto_ohlcv_ingestion",
        details={
            "provider": "coingecko",
            "vs_currency": resolved_settings.crypto_ohlcv_vs_currency,
            "days": resolved_settings.crypto_ohlcv_days,
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
                "missing_mapping_symbols": result.missing_mapping_symbols,
                "idempotent_skip": False,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for manual crypto OHLCV ingestion runs."""

    result = run_crypto_ohlcv_ingestion()
    logger.info(
        "crypto_ohlcv_ingestion_completed",
        extra={
            "processed_symbols": result.processed_symbols,
            "ingested_rows": result.ingested_rows,
            "skipped_rows": result.skipped_rows,
            "failed_symbols": result.failed_symbols,
            "no_data_symbols": result.no_data_symbols,
            "missing_mapping_symbols": result.missing_mapping_symbols,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "crypto_ohlcv_ingestion:"
        f" processed_symbols={result.processed_symbols}"
        f" ingested_rows={result.ingested_rows}"
        f" skipped_rows={result.skipped_rows}"
        f" failed_symbols={result.failed_symbols}"
        f" no_data_symbols={result.no_data_symbols}"
        f" missing_mapping_symbols={result.missing_mapping_symbols}"
        f" idempotent_skip={result.idempotent_skip}"
    )


def _active_crypto_symbol_fingerprint(session_factory: SessionFactory) -> str:
    symbols: list[str]
    with session_factory() as session:
        symbols = sorted(
            session.scalars(
                select(Asset.symbol).where(Asset.asset_type == "crypto", Asset.active.is_(True))
            ).all()
        )

    if not symbols:
        return "none"
    return "|".join(symbols)


def _persist_crypto_candles_for_asset(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    source: str,
    ingest_id: str,
    candles: list[CryptoCandlePoint],
) -> tuple[int, int]:
    """Persist crypto candles for one asset, skipping rows that already exist."""
    return persist_normalized_prices(
        session_factory,
        asset_id=asset_id,
        source=source,
        ingest_id=ingest_id,
        points=candles,
    )


if __name__ == "__main__":
    main()
