"""Tests for dependency-aware health endpoint behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market_screener.main import app

client = TestClient(app)


def test_health_route_returns_200_for_healthy_runtime(monkeypatch) -> None:
    expected_payload = {
        "status": "ok",
        "timestamp": "2026-04-22T00:00:00+00:00",
        "checks": {
            "database": {"status": "up", "latency_ms": 12, "error": None},
            "redis": {"status": "up", "latency_ms": 4, "error": None},
        },
    }

    monkeypatch.setattr(
        "market_screener.api.routes.system.evaluate_runtime_health",
        lambda _settings: expected_payload,
    )

    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert response.headers.get("X-Request-ID")


def test_health_route_returns_503_when_any_dependency_is_down(monkeypatch) -> None:
    expected_payload = {
        "status": "degraded",
        "timestamp": "2026-04-22T00:00:00+00:00",
        "checks": {
            "database": {"status": "up", "latency_ms": 10, "error": None},
            "redis": {"status": "down", "latency_ms": 2000, "error": "connection refused"},
        },
    }

    monkeypatch.setattr(
        "market_screener.api.routes.system.evaluate_runtime_health",
        lambda _settings: expected_payload,
    )

    response = client.get("/api/v1/system/health")

    assert response.status_code == 503
    assert response.json() == expected_payload
