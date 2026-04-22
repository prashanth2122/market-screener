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


def test_builds_database_and_redis_urls_from_components(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_provider_quota_settings_support_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER_QUOTA_RESERVE_RATIO", "0.2")
    monkeypatch.setenv("ALPHA_VANTAGE_QUOTA_PER_MINUTE", "10")
    monkeypatch.setenv("FINNHUB_QUOTA_PER_MINUTE", "80")

    settings = reload_settings()

    assert settings.provider_quota_reserve_ratio == 0.2
    assert settings.alpha_vantage_quota_per_minute == 10
    assert settings.finnhub_quota_per_minute == 80
