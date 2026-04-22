"""Unit tests for health check aggregation logic."""

from __future__ import annotations

from market_screener.core.health import evaluate_runtime_health
from market_screener.core.settings import Settings


def test_evaluate_runtime_health_returns_ok_when_all_checks_up(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_screener.core.health.check_postgres",
        lambda _database_url: {"status": "up", "latency_ms": 5, "error": None},
    )
    monkeypatch.setattr(
        "market_screener.core.health.check_redis",
        lambda _redis_url: {"status": "up", "latency_ms": 3, "error": None},
    )

    payload = evaluate_runtime_health(Settings())

    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "up"
    assert payload["checks"]["redis"]["status"] == "up"


def test_evaluate_runtime_health_returns_degraded_when_one_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_screener.core.health.check_postgres",
        lambda _database_url: {"status": "up", "latency_ms": 5, "error": None},
    )
    monkeypatch.setattr(
        "market_screener.core.health.check_redis",
        lambda _redis_url: {"status": "down", "latency_ms": 2000, "error": "timeout"},
    )

    payload = evaluate_runtime_health(Settings())

    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "up"
    assert payload["checks"]["redis"]["status"] == "down"
