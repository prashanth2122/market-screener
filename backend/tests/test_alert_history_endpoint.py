"""Tests for alert history API endpoint behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from market_screener.main import app

client = TestClient(app)


def test_alert_history_endpoint_filters_by_channel_and_paginates(monkeypatch) -> None:
    events = [
        {
            "id": "run-3:0",
            "run_id": "run-3",
            "channel": "telegram",
            "symbol": "AAPL",
            "status": "completed",
            "as_of_ts": "2026-04-24T09:00:00+00:00",
            "sent_at": "2026-04-24T09:05:00+00:00",
            "job_started_at": "2026-04-24T09:05:00+00:00",
            "job_finished_at": "2026-04-24T09:06:00+00:00",
        },
        {
            "id": "run-2:0",
            "run_id": "run-2",
            "channel": "email",
            "symbol": "AAPL",
            "status": "completed",
            "as_of_ts": "2026-04-24T08:00:00+00:00",
            "sent_at": "2026-04-24T08:05:00+00:00",
            "job_started_at": "2026-04-24T08:05:00+00:00",
            "job_finished_at": "2026-04-24T08:06:00+00:00",
        },
        {
            "id": "run-1:0",
            "run_id": "run-1",
            "channel": "telegram",
            "symbol": "BTC",
            "status": "completed",
            "as_of_ts": "2026-04-24T07:00:00+00:00",
            "sent_at": "2026-04-24T07:05:00+00:00",
            "job_started_at": "2026-04-24T07:05:00+00:00",
            "job_finished_at": "2026-04-24T07:06:00+00:00",
        },
    ]

    monkeypatch.setattr(
        "market_screener.api.routes.alert_history._read_alert_history_events",
        lambda *_args, **_kwargs: events,
    )

    response = client.get("/api/v1/alerts/history?channel=telegram&limit=1&offset=1")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["filters"]["channel"] == "telegram"
    assert payload["pagination"]["total"] == 2
    assert payload["pagination"]["returned"] == 1
    assert payload["items"][0]["id"] == "run-1:0"


def test_alert_history_endpoint_filters_symbol_case_insensitive(monkeypatch) -> None:
    events = [
        {
            "id": "run-2:0",
            "run_id": "run-2",
            "channel": "email",
            "symbol": "AAPL",
            "status": "completed",
            "as_of_ts": "2026-04-24T08:00:00+00:00",
            "sent_at": "2026-04-24T08:05:00+00:00",
            "job_started_at": "2026-04-24T08:05:00+00:00",
            "job_finished_at": "2026-04-24T08:06:00+00:00",
        },
        {
            "id": "run-1:0",
            "run_id": "run-1",
            "channel": "telegram",
            "symbol": "BTC",
            "status": "completed",
            "as_of_ts": "2026-04-24T07:00:00+00:00",
            "sent_at": "2026-04-24T07:05:00+00:00",
            "job_started_at": "2026-04-24T07:05:00+00:00",
            "job_finished_at": "2026-04-24T07:06:00+00:00",
        },
    ]

    monkeypatch.setattr(
        "market_screener.api.routes.alert_history._read_alert_history_events",
        lambda *_args, **_kwargs: events,
    )

    response = client.get("/api/v1/alerts/history?symbol=aapl")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["items"][0]["symbol"] == "AAPL"


def test_alert_history_endpoint_passes_since_hours_to_loader(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def _loader(*_args, **kwargs):
        captured["since_hours"] = kwargs["since_hours"]
        return []

    monkeypatch.setattr(
        "market_screener.api.routes.alert_history._read_alert_history_events",
        _loader,
    )

    response = client.get("/api/v1/alerts/history?since_hours=48")
    assert response.status_code == 200
    assert captured["since_hours"] == 48


def test_alert_history_endpoint_rejects_invalid_channel_filter() -> None:
    response = client.get("/api/v1/alerts/history?channel=sms")
    assert response.status_code == 422
