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

    # Pipeline tuning
    ingestion_swing_interval_seconds: int = 300
    news_poll_interval_seconds: int = 900
    fundamentals_refresh_hours: int = 24
    symbol_universe_file: str = "config/symbols_v1.json"

    # HTTP policy
    http_connect_timeout_seconds: int = 5
    http_read_timeout_seconds: int = 12
    http_total_timeout_seconds: int = 15
    http_retry_attempts: int = 3
    http_backoff_seconds: str = "1,2,4"
    provider_quota_reserve_ratio: float = 0.1
    alpha_vantage_quota_per_minute: int = 5
    finnhub_quota_per_minute: int = 60

    # Staleness/cache
    price_cache_ttl_seconds: int = 60
    news_cache_ttl_seconds: int = 900
    fundamentals_cache_ttl_seconds: int = 86400
    max_stale_price_minutes: int = 15
    max_stale_fundamentals_days: int = 7
    max_stale_news_hours: int = 24

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
