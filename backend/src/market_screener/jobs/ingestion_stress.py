"""Stress test workflow for ingestion pipelines."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.trading_calendar import TradingCalendar
from market_screener.db.models.core import Asset
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.crypto_ohlcv import CryptoOhlcvIngestionJob
from market_screener.jobs.equity_ohlcv import EquityOhlcvIngestionJob
from market_screener.jobs.macro_ohlcv import MacroOhlcvIngestionJob
from market_screener.providers.alpha_vantage import AlphaVantageClient
from market_screener.providers.coingecko import CoinGeckoClient
from market_screener.providers.finnhub import FinnhubClient

logger = logging.getLogger("market_screener.jobs.ingestion_stress")

FinnhubClientFactory = Callable[[], FinnhubClient]
CoinGeckoClientFactory = Callable[[], CoinGeckoClient]
AlphaVantageClientFactory = Callable[[], AlphaVantageClient]


@dataclass(frozen=True)
class IngestionStressSegmentResult:
    """Per-segment stress test metrics."""

    segment: str
    duration_ms: int
    processed_symbols: int
    ingested_rows: int
    skipped_rows: int
    failed_symbols: int
    no_data_symbols: int
    market_closed_symbols: int = 0
    missing_mapping_symbols: int = 0
    unsupported_symbols: int = 0


@dataclass(frozen=True)
class IngestionStressResult:
    """Overall ingestion stress test metrics."""

    symbol_limit: int
    symbols_under_test: int
    total_duration_ms: int
    processed_symbols: int
    ingested_rows: int
    skipped_rows: int
    failed_symbols: int
    no_data_symbols: int
    market_closed_symbols: int
    missing_mapping_symbols: int
    unsupported_symbols: int
    segments: list[IngestionStressSegmentResult]

    @property
    def overall_success(self) -> bool:
        """True when no segment reported symbol failures."""

        return self.processed_symbols > 0 and self.failed_symbols == 0


class IngestionStressTestJob:
    """Run bounded ingestion stress tests across all asset segments."""

    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        symbol_limit: int,
        finnhub_client_factory: FinnhubClientFactory | None = None,
        coingecko_client_factory: CoinGeckoClientFactory | None = None,
        alpha_vantage_client_factory: AlphaVantageClientFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._symbol_limit = max(1, symbol_limit)
        self._finnhub_client_factory = finnhub_client_factory or (
            lambda: FinnhubClient.from_settings(settings)
        )
        self._coingecko_client_factory = coingecko_client_factory or (
            lambda: CoinGeckoClient.from_settings(settings)
        )
        self._alpha_vantage_client_factory = alpha_vantage_client_factory or (
            lambda: AlphaVantageClient.from_settings(settings)
        )

    def run(self, *, now_utc: datetime | None = None) -> IngestionStressResult:
        """Run stress pass for up to `symbol_limit` active assets."""

        reference_now = now_utc or datetime.now(UTC)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=UTC)
        run_started = time.perf_counter()
        symbols = self._load_active_symbols(self._symbol_limit)
        symbol_allowlist = set(symbols)
        trading_calendar = TradingCalendar.from_settings(self._settings)

        if not symbol_allowlist:
            return IngestionStressResult(
                symbol_limit=self._symbol_limit,
                symbols_under_test=0,
                total_duration_ms=0,
                processed_symbols=0,
                ingested_rows=0,
                skipped_rows=0,
                failed_symbols=0,
                no_data_symbols=0,
                market_closed_symbols=0,
                missing_mapping_symbols=0,
                unsupported_symbols=0,
                segments=[],
            )

        equity_job = EquityOhlcvIngestionJob(
            self._session_factory,
            self._finnhub_client_factory,
            resolution=self._settings.equity_ohlcv_resolution,
            lookback_days=self._settings.equity_ohlcv_lookback_days,
            trading_calendar=trading_calendar,
            symbol_allowlist=symbol_allowlist,
        )
        crypto_job = CryptoOhlcvIngestionJob(
            self._session_factory,
            self._coingecko_client_factory,
            symbol_map_path=Path(self._settings.symbol_universe_file),
            vs_currency=self._settings.crypto_ohlcv_vs_currency,
            days=self._settings.crypto_ohlcv_days,
            symbol_allowlist=symbol_allowlist,
        )
        macro_job = MacroOhlcvIngestionJob(
            self._session_factory,
            self._alpha_vantage_client_factory,
            lookback_days=self._settings.macro_ohlcv_lookback_days,
            forex_outputsize=self._settings.macro_ohlcv_forex_outputsize,
            commodity_interval=self._settings.macro_ohlcv_commodity_interval,
            trading_calendar=trading_calendar,
            symbol_allowlist=symbol_allowlist,
        )

        segments: list[IngestionStressSegmentResult] = []

        equity_started = time.perf_counter()
        equity_result = equity_job.run(now_utc=reference_now)
        segments.append(
            IngestionStressSegmentResult(
                segment="equity",
                duration_ms=int((time.perf_counter() - equity_started) * 1000),
                processed_symbols=equity_result.processed_symbols,
                ingested_rows=equity_result.ingested_rows,
                skipped_rows=equity_result.skipped_rows,
                failed_symbols=equity_result.failed_symbols,
                no_data_symbols=equity_result.no_data_symbols,
                market_closed_symbols=equity_result.market_closed_symbols,
            )
        )

        crypto_started = time.perf_counter()
        crypto_result = crypto_job.run(now_utc=reference_now)
        segments.append(
            IngestionStressSegmentResult(
                segment="crypto",
                duration_ms=int((time.perf_counter() - crypto_started) * 1000),
                processed_symbols=crypto_result.processed_symbols,
                ingested_rows=crypto_result.ingested_rows,
                skipped_rows=crypto_result.skipped_rows,
                failed_symbols=crypto_result.failed_symbols,
                no_data_symbols=crypto_result.no_data_symbols,
                missing_mapping_symbols=crypto_result.missing_mapping_symbols,
            )
        )

        macro_started = time.perf_counter()
        macro_result = macro_job.run(now_utc=reference_now)
        segments.append(
            IngestionStressSegmentResult(
                segment="macro",
                duration_ms=int((time.perf_counter() - macro_started) * 1000),
                processed_symbols=macro_result.processed_symbols,
                ingested_rows=macro_result.ingested_rows,
                skipped_rows=macro_result.skipped_rows,
                failed_symbols=macro_result.failed_symbols,
                no_data_symbols=macro_result.no_data_symbols,
                market_closed_symbols=macro_result.market_closed_symbols,
                unsupported_symbols=macro_result.unsupported_symbols,
            )
        )

        return IngestionStressResult(
            symbol_limit=self._symbol_limit,
            symbols_under_test=len(symbol_allowlist),
            total_duration_ms=int((time.perf_counter() - run_started) * 1000),
            processed_symbols=sum(segment.processed_symbols for segment in segments),
            ingested_rows=sum(segment.ingested_rows for segment in segments),
            skipped_rows=sum(segment.skipped_rows for segment in segments),
            failed_symbols=sum(segment.failed_symbols for segment in segments),
            no_data_symbols=sum(segment.no_data_symbols for segment in segments),
            market_closed_symbols=sum(segment.market_closed_symbols for segment in segments),
            missing_mapping_symbols=sum(segment.missing_mapping_symbols for segment in segments),
            unsupported_symbols=sum(segment.unsupported_symbols for segment in segments),
            segments=segments,
        )

    def _load_active_symbols(self, symbol_limit: int) -> list[str]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Asset.symbol)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(symbol_limit)
                ).all()
            )


def run_ingestion_stress_test(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
    finnhub_client_factory: FinnhubClientFactory | None = None,
    coingecko_client_factory: CoinGeckoClientFactory | None = None,
    alpha_vantage_client_factory: AlphaVantageClientFactory | None = None,
) -> IngestionStressResult:
    """Run ingestion stress test with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = now_utc or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)

    job = IngestionStressTestJob(
        resolved_session_factory,
        resolved_settings,
        symbol_limit=resolved_settings.ingestion_stress_symbol_limit,
        finnhub_client_factory=finnhub_client_factory,
        coingecko_client_factory=coingecko_client_factory,
        alpha_vantage_client_factory=alpha_vantage_client_factory,
    )
    with resolved_audit.track_job_run(
        "ingestion_stress_test",
        details={
            "symbol_limit": resolved_settings.ingestion_stress_symbol_limit,
            "window_anchor": reference_now.date().isoformat(),
            "purpose": "day39_ingestion_stress",
        },
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "symbols_under_test": result.symbols_under_test,
                "processed_symbols": result.processed_symbols,
                "ingested_rows": result.ingested_rows,
                "skipped_rows": result.skipped_rows,
                "failed_symbols": result.failed_symbols,
                "no_data_symbols": result.no_data_symbols,
                "market_closed_symbols": result.market_closed_symbols,
                "missing_mapping_symbols": result.missing_mapping_symbols,
                "unsupported_symbols": result.unsupported_symbols,
                "total_duration_ms": result.total_duration_ms,
                "overall_success": result.overall_success,
                "segments": [
                    {
                        "segment": segment.segment,
                        "processed_symbols": segment.processed_symbols,
                        "ingested_rows": segment.ingested_rows,
                        "failed_symbols": segment.failed_symbols,
                        "duration_ms": segment.duration_ms,
                    }
                    for segment in result.segments
                ],
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for ingestion stress test."""

    result = run_ingestion_stress_test()
    logger.info(
        "ingestion_stress_test_completed",
        extra={
            "symbol_limit": result.symbol_limit,
            "symbols_under_test": result.symbols_under_test,
            "processed_symbols": result.processed_symbols,
            "failed_symbols": result.failed_symbols,
            "ingested_rows": result.ingested_rows,
            "total_duration_ms": result.total_duration_ms,
            "overall_success": result.overall_success,
        },
    )
    print(
        "ingestion_stress_test:"
        f" symbol_limit={result.symbol_limit}"
        f" symbols_under_test={result.symbols_under_test}"
        f" processed_symbols={result.processed_symbols}"
        f" ingested_rows={result.ingested_rows}"
        f" skipped_rows={result.skipped_rows}"
        f" failed_symbols={result.failed_symbols}"
        f" no_data_symbols={result.no_data_symbols}"
        f" market_closed_symbols={result.market_closed_symbols}"
        f" missing_mapping_symbols={result.missing_mapping_symbols}"
        f" unsupported_symbols={result.unsupported_symbols}"
        f" total_duration_ms={result.total_duration_ms}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
