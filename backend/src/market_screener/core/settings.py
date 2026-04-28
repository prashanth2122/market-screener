"""Configuration management for backend runtime settings."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SENSITIVE_FIELDS = {
    "app_secret_key",
    "auth_basic_password",
    "postgres_password",
    "redis_password",
    "fmp_api_key",
    "finnhub_api_key",
    "alpha_vantage_api_key",
    "marketaux_api_key",
    "coingecko_api_key",
    "ccxt_api_key",
    "ccxt_api_secret",
    "telegram_bot_token",
    "smtp_password",
}


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables with sensible defaults."""

    # Core app
    app_name: str = "market-screener"
    app_env: str = "development"
    tz: str = "Asia/Kolkata"
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"

    # Runtime services
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_host: str = "0.0.0.0"
    frontend_port: int = 3000

    # Auth/security
    auth_enabled: bool = True
    auth_basic_username: str = "prash"
    auth_basic_password: str = "change_me_strong_password"
    app_secret_key: str = "replace_with_long_random_secret"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "market_screener"
    postgres_user: str = "market_user"
    postgres_password: str = "change_me_postgres_password"
    database_url: str | None = None

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_url: str | None = None

    # Provider keys/settings
    fmp_api_key: str | None = None
    finnhub_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    marketaux_api_key: str | None = None
    coingecko_api_key: str | None = None
    ccxt_exchange_id: str = "binance"
    ccxt_api_key: str | None = None
    ccxt_api_secret: str | None = None

    # Alerts
    alert_channel_telegram_enabled: bool = True
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    alert_max_per_day: int = 5
    alert_cooldown_minutes: int = 60
    alert_channel_email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    alert_dispatch_symbol_limit: int = 150
    alert_dispatch_lookback_hours: int = 72
    alert_dispatch_signal_allowlist: str = "strong_buy,buy"
    alert_dispatch_min_score: float = 70.0

    # Pipeline tuning
    ingestion_swing_interval_seconds: int = 300
    news_poll_interval_seconds: int = 900
    fundamentals_refresh_hours: int = 24
    symbol_universe_file: str = "config/symbols_v1.json"
    watchlist_symbols: str = ""
    market_holidays_us: str = ""
    market_holidays_nse: str = ""
    market_holidays_global: str = ""
    freshness_monitor_target_age_minutes: int = 5
    freshness_monitor_symbol_limit: int = 20
    provider_health_lookback_hours: int = 24
    provider_health_job_sample_limit: int = 500
    provider_health_dashboard_history_limit: int = 24
    ingestion_stress_symbol_limit: int = 100
    indicator_snapshot_symbol_limit: int = 150
    indicator_snapshot_price_lookback_rows: int = 260
    indicator_snapshot_source: str = "ta_v1"
    trend_regime_symbol_limit: int = 150
    trend_regime_indicator_source: str = "ta_v1"
    trend_regime_macd_flat_tolerance: float = 0.10
    breakout_symbol_limit: int = 150
    breakout_lookback_bars: int = 20
    breakout_buffer_ratio: float = 0.002
    breakout_indicator_source: str = "ta_v1"
    relative_volume_symbol_limit: int = 150
    relative_volume_lookback_bars: int = 20
    relative_volume_spike_threshold: float = 1.5
    relative_volume_dry_up_threshold: float = 0.7
    fundamentals_snapshot_symbol_limit: int = 150
    fundamentals_snapshot_period_type: str = "annual"
    fundamentals_snapshot_limit_per_symbol: int = 2
    fundamentals_snapshot_source: str = "fmp_v1"
    news_ingestion_symbol_limit: int = 150
    news_ingestion_limit_per_symbol: int = 5
    news_ingestion_lookback_hours: int = 72
    news_ingestion_language: str = "en"
    news_ingestion_source: str = "marketaux_v1"
    sentiment_pipeline_symbol_limit: int = 150
    sentiment_pipeline_lookback_hours: int = 72
    sentiment_pipeline_half_life_hours: int = 24
    sentiment_pipeline_source_filter: str = "marketaux_v1"
    event_risk_symbol_limit: int = 150
    event_risk_lookback_hours: int = 72
    event_risk_source_filter: str = "marketaux_v1"
    event_risk_negative_sentiment_threshold: float = -0.35
    score_backfill_symbol_limit: int = 150
    score_backfill_lookback_days: int = 90
    score_backfill_indicator_source: str = "ta_v1"
    score_backfill_fundamentals_source: str = "fmp_v1"
    score_backfill_news_source_filter: str = "marketaux_v1"
    score_backfill_news_lookback_hours: int = 72
    score_backfill_sentiment_half_life_hours: int = 24
    equity_ohlcv_resolution: str = "D"
    equity_ohlcv_lookback_days: int = 365
    crypto_ohlcv_vs_currency: str = "usd"
    crypto_ohlcv_days: int = 365
    macro_ohlcv_lookback_days: int = 365
    macro_ohlcv_forex_outputsize: str = "full"
    macro_ohlcv_commodity_interval: str = "daily"
    backfill_validation_symbol_limit: int = 20
    backfill_validation_lookback_days: int = 7
    backfill_validation_min_rows: int = 3
    backfill_validation_max_last_row_age_days: int = 4
    ingestion_failure_retry_backoff_minutes: str = "5,15,60"
    ingestion_failure_max_attempts: int = 5
    ingestion_failure_retry_batch_size: int = 50

    # HTTP policy
    http_connect_timeout_seconds: int = 5
    http_read_timeout_seconds: int = 12
    http_total_timeout_seconds: int = 15
    http_retry_attempts: int = 3
    http_backoff_seconds: str = "1,2,4"
    provider_quota_reserve_ratio: float = 0.1
    fmp_quota_per_minute: int = 60
    alpha_vantage_quota_per_minute: int = 5
    finnhub_quota_per_minute: int = 60
    coingecko_quota_per_minute: int = 30
    marketaux_quota_per_minute: int = 30

    # Staleness/cache
    price_cache_ttl_seconds: int = 60
    news_cache_ttl_seconds: int = 900
    fundamentals_cache_ttl_seconds: int = 86400

    # API response cache (dashboard)
    api_cache_enabled: bool = True
    api_cache_max_entries: int = 2000
    api_cache_screener_ttl_seconds: int = 10
    api_cache_asset_detail_ttl_seconds: int = 15
    max_stale_price_minutes: int = 15
    max_stale_fundamentals_days: int = 7
    max_stale_news_hours: int = 24

    # DB profiling
    db_slow_query_log_enabled: bool = True
    db_slow_query_threshold_ms: int = 250
    db_slow_query_max_entries: int = 200
    db_slow_query_max_sql_chars: int = 600
    db_slow_query_endpoint_enabled: bool = False

    # Daily digest (Day 95)
    daily_digest_telegram_enabled: bool = True
    daily_digest_email_enabled: bool = False
    daily_digest_symbol_limit: int = 50
    daily_digest_lookback_hours: int = 24
    daily_digest_signal_allowlist: str | None = None
    daily_digest_min_score: float | None = None
    daily_digest_include_blocked_by_risk: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _finalize(self) -> "Settings":
        """Normalize and derive config values after parsing env inputs."""

        self.log_level = self.log_level.upper()

        if not self.database_url:
            user = quote_plus(self.postgres_user)
            password = quote_plus(self.postgres_password)
            self.database_url = f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        if not self.redis_url:
            if self.redis_password:
                password = quote_plus(self.redis_password)
                self.redis_url = (
                    f"redis://:{password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
                )
            else:
                self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """SQLAlchemy-ready DSN with explicit psycopg driver."""

        assert self.database_url is not None
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def is_production(self) -> bool:
        """Convenience flag for environment checks."""

        return self.app_env.lower() == "production"

    def as_safe_dict(self) -> dict[str, object]:
        """Return settings with sensitive values redacted for logging/debug."""

        data = self.model_dump()
        for field_name in _SENSITIVE_FIELDS:
            if field_name in data and data[field_name]:
                data[field_name] = "***REDACTED***"
        if isinstance(data.get("database_url"), str):
            data["database_url"] = _redact_url_password(data["database_url"])
        if isinstance(data.get("redis_url"), str):
            data["redis_url"] = _redact_url_password(data["redis_url"])
        return data


def _redact_url_password(value: str) -> str:
    """Mask password section in a URL while preserving host/db context."""

    parts = urlsplit(value)
    if not parts.netloc or "@" not in parts.netloc:
        return value

    credentials, host = parts.netloc.rsplit("@", 1)
    if ":" in credentials:
        user = credentials.split(":", 1)[0]
        safe_netloc = f"{user}:***REDACTED***@{host}"
    else:
        safe_netloc = f"{credentials}@{host}"
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for process lifetime."""

    return Settings()


def reload_settings() -> Settings:
    """Clear settings cache and reload from current environment."""

    get_settings.cache_clear()
    return get_settings()
