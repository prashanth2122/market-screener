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
            "redis": {
                "status": "down",
                "latency_ms": 2000,
                "error": "connection refused",
            },
        },
    }

    monkeypatch.setattr(
        "market_screener.api.routes.system.evaluate_runtime_health",
        lambda _settings: expected_payload,
    )

    response = client.get("/api/v1/system/health")

    assert response.status_code == 503
    assert response.json() == expected_payload


def test_provider_health_route_returns_dashboard_payload(monkeypatch) -> None:
    expected_payload = {
        "status": "ok",
        "window_start": "2026-04-23T00:00:00+00:00",
        "window_end": "2026-04-23T12:00:00+00:00",
        "provider_count": 1,
        "providers": [
            {
                "provider_name": "finnhub",
                "latest": {
                    "ts": "2026-04-23T11:55:00+00:00",
                    "latency_ms": 1200,
                    "success_rate": 95.0,
                    "error_count": 0,
                },
                "history": [],
            }
        ],
    }

    monkeypatch.setattr(
        "market_screener.api.routes.system.read_provider_health_dashboard",
        lambda *_args, **_kwargs: expected_payload,
    )

    response = client.get("/api/v1/system/provider-health")

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_provider_health_refresh_route_returns_refresh_summary(monkeypatch) -> None:
    class FakeResult:
        provider_count = 2
        lookback_hours = 24
        sample_limit = 500
        providers = [
            type("Snapshot", (), {"provider_name": "alpha_vantage"})(),
            type("Snapshot", (), {"provider_name": "finnhub"})(),
        ]

    monkeypatch.setattr(
        "market_screener.api.routes.system.run_provider_health_dashboard",
        lambda **_kwargs: FakeResult(),
    )

    response = client.post("/api/v1/system/provider-health/refresh")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "provider_count": 2,
        "providers": ["alpha_vantage", "finnhub"],
        "lookback_hours": 24,
        "sample_limit": 500,
    }
