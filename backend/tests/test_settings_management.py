"""Tests for config management behavior."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from market_screener.core.settings import get_settings, reload_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Ensure each test evaluates settings from fresh cache."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_builds_database_and_redis_urls_from_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("POSTGRES_HOST", "pg-host")
    monkeypatch.setenv("POSTGRES_PORT", "5544")
    monkeypatch.setenv("POSTGRES_DB", "unit_db")
    monkeypatch.setenv("POSTGRES_USER", "unit_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "unit_pw")
    monkeypatch.setenv("REDIS_HOST", "redis-host")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "5")

    settings = reload_settings()

    assert settings.database_url == "postgresql://unit_user:unit_pw@pg-host:5544/unit_db"
    assert (
        settings.sqlalchemy_database_url
        == "postgresql+psycopg://unit_user:unit_pw@pg-host:5544/unit_db"
    )
    assert settings.redis_url == "redis://redis-host:6380/5"


def test_respects_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@localhost:5432/custom_db")
    settings = reload_settings()

    assert settings.database_url == "postgresql://user:pw@localhost:5432/custom_db"
    assert (
        settings.sqlalchemy_database_url == "postgresql+psycopg://user:pw@localhost:5432/custom_db"
    )


def test_safe_dump_redacts_sensitive_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "super-secret")
    monkeypatch.setenv("AUTH_BASIC_PASSWORD", "top-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://:rpass@localhost:6379/0")

    settings = reload_settings()
    safe_data = settings.as_safe_dict()

    assert safe_data["app_secret_key"] == "***REDACTED***"
    assert safe_data["auth_basic_password"] == "***REDACTED***"
    assert safe_data["database_url"] == "postgresql://user:***REDACTED***@localhost:5432/db"
    assert safe_data["redis_url"] == "redis://:***REDACTED***@localhost:6379/0"


def test_provider_quota_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_QUOTA_RESERVE_RATIO", "0.2")
    monkeypatch.setenv("FMP_QUOTA_PER_MINUTE", "70")
    monkeypatch.setenv("ALPHA_VANTAGE_QUOTA_PER_MINUTE", "10")
    monkeypatch.setenv("FINNHUB_QUOTA_PER_MINUTE", "80")
    monkeypatch.setenv("COINGECKO_QUOTA_PER_MINUTE", "45")

    settings = reload_settings()

    assert settings.provider_quota_reserve_ratio == 0.2
    assert settings.fmp_quota_per_minute == 70
    assert settings.alpha_vantage_quota_per_minute == 10
    assert settings.finnhub_quota_per_minute == 80
    assert settings.coingecko_quota_per_minute == 45


def test_ingestion_failure_retry_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGESTION_FAILURE_RETRY_BACKOFF_MINUTES", "2,4,8")
    monkeypatch.setenv("INGESTION_FAILURE_MAX_ATTEMPTS", "6")
    monkeypatch.setenv("INGESTION_FAILURE_RETRY_BATCH_SIZE", "25")

    settings = reload_settings()

    assert settings.ingestion_failure_retry_backoff_minutes == "2,4,8"
    assert settings.ingestion_failure_max_attempts == 6
    assert settings.ingestion_failure_retry_batch_size == 25


def test_backfill_validation_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKFILL_VALIDATION_SYMBOL_LIMIT", "15")
    monkeypatch.setenv("BACKFILL_VALIDATION_LOOKBACK_DAYS", "10")
    monkeypatch.setenv("BACKFILL_VALIDATION_MIN_ROWS", "4")
    monkeypatch.setenv("BACKFILL_VALIDATION_MAX_LAST_ROW_AGE_DAYS", "3")

    settings = reload_settings()

    assert settings.backfill_validation_symbol_limit == 15
    assert settings.backfill_validation_lookback_days == 10
    assert settings.backfill_validation_min_rows == 4
    assert settings.backfill_validation_max_last_row_age_days == 3


def test_crypto_ohlcv_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRYPTO_OHLCV_VS_CURRENCY", "inr")
    monkeypatch.setenv("CRYPTO_OHLCV_DAYS", "90")

    settings = reload_settings()

    assert settings.crypto_ohlcv_vs_currency == "inr"
    assert settings.crypto_ohlcv_days == 90


def test_macro_ohlcv_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MACRO_OHLCV_LOOKBACK_DAYS", "120")
    monkeypatch.setenv("MACRO_OHLCV_FOREX_OUTPUTSIZE", "compact")
    monkeypatch.setenv("MACRO_OHLCV_COMMODITY_INTERVAL", "monthly")

    settings = reload_settings()

    assert settings.macro_ohlcv_lookback_days == 120
    assert settings.macro_ohlcv_forex_outputsize == "compact"
    assert settings.macro_ohlcv_commodity_interval == "monthly"


def test_trading_holiday_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_HOLIDAYS_US", "2026-01-01,2026-12-25")
    monkeypatch.setenv("MARKET_HOLIDAYS_NSE", "2026-08-15")
    monkeypatch.setenv("MARKET_HOLIDAYS_GLOBAL", "2026-01-01")

    settings = reload_settings()

    assert settings.market_holidays_us == "2026-01-01,2026-12-25"
    assert settings.market_holidays_nse == "2026-08-15"
    assert settings.market_holidays_global == "2026-01-01"


def test_freshness_monitor_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WATCHLIST_SYMBOLS", "AAPL,BTC,RELIANCE")
    monkeypatch.setenv("FRESHNESS_MONITOR_TARGET_AGE_MINUTES", "7")
    monkeypatch.setenv("FRESHNESS_MONITOR_SYMBOL_LIMIT", "30")

    settings = reload_settings()

    assert settings.watchlist_symbols == "AAPL,BTC,RELIANCE"
    assert settings.freshness_monitor_target_age_minutes == 7
    assert settings.freshness_monitor_symbol_limit == 30


def test_provider_health_dashboard_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_HEALTH_LOOKBACK_HOURS", "12")
    monkeypatch.setenv("PROVIDER_HEALTH_JOB_SAMPLE_LIMIT", "300")
    monkeypatch.setenv("PROVIDER_HEALTH_DASHBOARD_HISTORY_LIMIT", "48")

    settings = reload_settings()

    assert settings.provider_health_lookback_hours == 12
    assert settings.provider_health_job_sample_limit == 300
    assert settings.provider_health_dashboard_history_limit == 48


def test_ingestion_stress_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGESTION_STRESS_SYMBOL_LIMIT", "120")

    settings = reload_settings()

    assert settings.ingestion_stress_symbol_limit == 120


def test_indicator_snapshot_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INDICATOR_SNAPSHOT_SYMBOL_LIMIT", "90")
    monkeypatch.setenv("INDICATOR_SNAPSHOT_PRICE_LOOKBACK_ROWS", "320")
    monkeypatch.setenv("INDICATOR_SNAPSHOT_SOURCE", "ta_test")

    settings = reload_settings()

    assert settings.indicator_snapshot_symbol_limit == 90
    assert settings.indicator_snapshot_price_lookback_rows == 320
    assert settings.indicator_snapshot_source == "ta_test"


def test_trend_regime_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TREND_REGIME_SYMBOL_LIMIT", "120")
    monkeypatch.setenv("TREND_REGIME_INDICATOR_SOURCE", "ta_alt")
    monkeypatch.setenv("TREND_REGIME_MACD_FLAT_TOLERANCE", "0.2")

    settings = reload_settings()

    assert settings.trend_regime_symbol_limit == 120
    assert settings.trend_regime_indicator_source == "ta_alt"
    assert settings.trend_regime_macd_flat_tolerance == 0.2


def test_breakout_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BREAKOUT_SYMBOL_LIMIT", "80")
    monkeypatch.setenv("BREAKOUT_LOOKBACK_BARS", "30")
    monkeypatch.setenv("BREAKOUT_BUFFER_RATIO", "0.005")
    monkeypatch.setenv("BREAKOUT_INDICATOR_SOURCE", "ta_alt")

    settings = reload_settings()

    assert settings.breakout_symbol_limit == 80
    assert settings.breakout_lookback_bars == 30
    assert settings.breakout_buffer_ratio == 0.005
    assert settings.breakout_indicator_source == "ta_alt"


def test_relative_volume_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELATIVE_VOLUME_SYMBOL_LIMIT", "120")
    monkeypatch.setenv("RELATIVE_VOLUME_LOOKBACK_BARS", "30")
    monkeypatch.setenv("RELATIVE_VOLUME_SPIKE_THRESHOLD", "1.8")
    monkeypatch.setenv("RELATIVE_VOLUME_DRY_UP_THRESHOLD", "0.6")

    settings = reload_settings()

    assert settings.relative_volume_symbol_limit == 120
    assert settings.relative_volume_lookback_bars == 30
    assert settings.relative_volume_spike_threshold == 1.8
    assert settings.relative_volume_dry_up_threshold == 0.6


def test_fundamentals_snapshot_settings_support_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FUNDAMENTALS_SNAPSHOT_SYMBOL_LIMIT", "75")
    monkeypatch.setenv("FUNDAMENTALS_SNAPSHOT_PERIOD_TYPE", "quarter")
    monkeypatch.setenv("FUNDAMENTALS_SNAPSHOT_LIMIT_PER_SYMBOL", "4")
    monkeypatch.setenv("FUNDAMENTALS_SNAPSHOT_SOURCE", "fmp_test")

    settings = reload_settings()

    assert settings.fundamentals_snapshot_symbol_limit == 75
    assert settings.fundamentals_snapshot_period_type == "quarter"
    assert settings.fundamentals_snapshot_limit_per_symbol == 4
    assert settings.fundamentals_snapshot_source == "fmp_test"
