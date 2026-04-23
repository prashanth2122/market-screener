"""Background jobs for ingestion and analytics pipelines."""

from market_screener.jobs.audit import JobAuditTrail, JobRunHandle
from market_screener.jobs.backfill_validation import (
    BackfillValidationResult,
    EquityBackfillValidationJob,
    SymbolBackfillStatus,
)
from market_screener.jobs.breakout_detection import (
    BreakoutAssetStatus,
    BreakoutDetectionJob,
    BreakoutDetectionResult,
    run_breakout_detection,
)
from market_screener.jobs.crypto_ohlcv import (
    CryptoCandlePoint,
    CryptoOhlcvIngestionJob,
    CryptoOhlcvIngestionResult,
    CryptoOhlcvParseError,
    CryptoSymbolMapParseError,
)
from market_screener.jobs.equity_ohlcv import (
    EquityOhlcvIngestionJob,
    EquityOhlcvIngestionResult,
    EquityOhlcvParseError,
)
from market_screener.jobs.freshness_monitor import (
    SymbolFreshnessStatus,
    WatchlistFreshnessMonitorJob,
    WatchlistFreshnessResult,
    parse_watchlist_symbols,
)
from market_screener.jobs.fundamentals_snapshot import (
    FundamentalsSnapshotParseError,
    FundamentalsSnapshotPullJob,
    FundamentalsSnapshotPullResult,
    run_fundamentals_snapshot_pull,
)
from market_screener.jobs.ingestion_adapters import (
    AdapterNormalizationError,
    AdapterSymbolMappingError,
    AlphaVantageMacroAdapter,
    CoinGeckoCryptoAdapter,
    CryptoIngestionAdapter,
    EquityIngestionAdapter,
    FinnhubEquityAdapter,
    MacroIngestionAdapter,
    build_alpha_vantage_macro_adapter_factory,
    build_coingecko_crypto_adapter_factory,
    build_finnhub_equity_adapter_factory,
)
from market_screener.jobs.idempotency import build_idempotency_key, file_sha256
from market_screener.jobs.ingestion_failures import (
    IngestionFailureItem,
    IngestionFailureStore,
)
from market_screener.jobs.ingestion_retry import (
    IngestionFailureRetryJob,
    IngestionRetryResult,
)
from market_screener.jobs.indicator_snapshot import (
    IndicatorSnapshotJob,
    IndicatorSnapshotWriteResult,
    run_indicator_snapshot_refresh,
)
from market_screener.jobs.ingestion_stress import (
    IngestionStressResult,
    IngestionStressSegmentResult,
    IngestionStressTestJob,
    run_ingestion_stress_test,
)
from market_screener.jobs.macro_ohlcv import (
    MacroCandlePoint,
    MacroOhlcvIngestionJob,
    MacroOhlcvIngestionResult,
    MacroOhlcvParseError,
)
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    PriceNormalizationError,
)
from market_screener.jobs.provider_health_dashboard import (
    ProviderHealthDashboardJob,
    ProviderHealthDashboardResult,
    ProviderHealthSnapshot,
    read_provider_health_dashboard,
    run_provider_health_dashboard,
)
from market_screener.jobs.relative_volume import (
    RelativeVolumeAssetStatus,
    RelativeVolumeJob,
    RelativeVolumeResult,
    run_relative_volume_calculation,
)
from market_screener.jobs.symbol_metadata import (
    SymbolIngestionResult,
    SymbolMetadataIngestionJob,
    SymbolRecord,
    SymbolUniverseParseError,
)
from market_screener.jobs.trend_regime import (
    TrendRegimeAssetStatus,
    TrendRegimeClassificationJob,
    TrendRegimeClassificationResult,
    run_trend_regime_classification,
)

__all__ = [
    "JobRunHandle",
    "JobAuditTrail",
    "SymbolBackfillStatus",
    "BackfillValidationResult",
    "EquityBackfillValidationJob",
    "BreakoutAssetStatus",
    "BreakoutDetectionResult",
    "BreakoutDetectionJob",
    "run_breakout_detection",
    "CryptoCandlePoint",
    "CryptoOhlcvParseError",
    "CryptoSymbolMapParseError",
    "CryptoOhlcvIngestionResult",
    "CryptoOhlcvIngestionJob",
    "MacroCandlePoint",
    "MacroOhlcvParseError",
    "MacroOhlcvIngestionResult",
    "MacroOhlcvIngestionJob",
    "NormalizedPricePoint",
    "PriceNormalizationError",
    "EquityOhlcvParseError",
    "EquityOhlcvIngestionResult",
    "EquityOhlcvIngestionJob",
    "parse_watchlist_symbols",
    "SymbolFreshnessStatus",
    "WatchlistFreshnessResult",
    "WatchlistFreshnessMonitorJob",
    "FundamentalsSnapshotParseError",
    "FundamentalsSnapshotPullResult",
    "FundamentalsSnapshotPullJob",
    "run_fundamentals_snapshot_pull",
    "AdapterNormalizationError",
    "AdapterSymbolMappingError",
    "EquityIngestionAdapter",
    "CryptoIngestionAdapter",
    "MacroIngestionAdapter",
    "FinnhubEquityAdapter",
    "CoinGeckoCryptoAdapter",
    "AlphaVantageMacroAdapter",
    "build_finnhub_equity_adapter_factory",
    "build_coingecko_crypto_adapter_factory",
    "build_alpha_vantage_macro_adapter_factory",
    "IngestionStressSegmentResult",
    "IngestionStressResult",
    "IngestionStressTestJob",
    "run_ingestion_stress_test",
    "ProviderHealthSnapshot",
    "ProviderHealthDashboardResult",
    "ProviderHealthDashboardJob",
    "read_provider_health_dashboard",
    "run_provider_health_dashboard",
    "RelativeVolumeAssetStatus",
    "RelativeVolumeResult",
    "RelativeVolumeJob",
    "run_relative_volume_calculation",
    "IngestionFailureItem",
    "IngestionFailureStore",
    "IngestionRetryResult",
    "IngestionFailureRetryJob",
    "IndicatorSnapshotWriteResult",
    "IndicatorSnapshotJob",
    "run_indicator_snapshot_refresh",
    "build_idempotency_key",
    "file_sha256",
    "SymbolRecord",
    "SymbolIngestionResult",
    "SymbolUniverseParseError",
    "SymbolMetadataIngestionJob",
    "TrendRegimeAssetStatus",
    "TrendRegimeClassificationResult",
    "TrendRegimeClassificationJob",
    "run_trend_regime_classification",
]
