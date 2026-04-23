"""Tests for ingestion job audit trail persistence."""

from __future__ import annotations

from typing import Any

import pytest

from market_screener.jobs.audit import JobAuditTrail


class FakeSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def add(self, job_row) -> None:
        self._store[job_row.run_id] = job_row

    def merge(self, job_row):
        self._store[job_row.run_id] = job_row
        return job_row

    def commit(self) -> None:
        self._store["_commits"] = self._store.get("_commits", 0) + 1


def _build_session_factory(store: dict[str, Any]):
    def _factory() -> FakeSession:
        return FakeSession(store)

    return _factory


def test_job_audit_trail_records_completed_run() -> None:
    store: dict[str, Any] = {}
    trail = JobAuditTrail(_build_session_factory(store))

    with trail.track_job_run("symbol_metadata_ingestion", details={"scope": "all"}) as run:
        run.add_details({"created": 2, "updated": 1})

    rows = [value for key, value in store.items() if key != "_commits"]
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "completed"
    assert row.finished_at is not None
    assert row.duration_ms is not None
    assert row.error_message is None
    assert row.details["scope"] == "all"
    assert row.details["created"] == 2


def test_job_audit_trail_records_failed_run() -> None:
    store: dict[str, Any] = {}
    trail = JobAuditTrail(_build_session_factory(store))

    with pytest.raises(RuntimeError):
        with trail.track_job_run("equity_ohlcv_ingestion", details={"provider": "finnhub"}):
            raise RuntimeError("synthetic failure")

    rows = [value for key, value in store.items() if key != "_commits"]
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failed"
    assert row.finished_at is not None
    assert row.duration_ms is not None
    assert row.error_message == "synthetic failure"
    assert row.details["provider"] == "finnhub"


def test_job_audit_trail_detects_completed_idempotency_key() -> None:
    store: dict[str, Any] = {}
    trail = JobAuditTrail(_build_session_factory(store))

    assert trail.has_completed_run("equity_ohlcv_ingestion", "same-key") is False

    with trail.track_job_run("equity_ohlcv_ingestion", idempotency_key="same-key"):
        pass

    assert trail.has_completed_run("equity_ohlcv_ingestion", "same-key") is True
    assert trail.has_completed_run("equity_ohlcv_ingestion", "different-key") is False
