"""Smoke tests for backend scaffold."""

from fastapi.testclient import TestClient

from market_screener.main import app

client = TestClient(app)


def test_root_route_bootstrapped() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "bootstrapped"
    assert response.headers.get("X-Request-ID")


def test_ping_route_ok() -> None:
    response = client.get("/api/v1/system/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_is_echoed_when_provided() -> None:
    response = client.get("/api/v1/system/ping", headers={"X-Request-ID": "req-test-001"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "req-test-001"
