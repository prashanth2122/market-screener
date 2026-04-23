"""Tests for provider health dashboard aggregation workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from market_screener.core.settings import Settings
from market_screener.db.models.core import Job, ProviderHealth
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.provider_health_dashboard import (
    ProviderHealthDashboardJob,
    read_provider_health_dashboard,
    run_provider_health_dashboard,
)


class FakeScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return list(self._values)


class FakeSession:
    def __init__(self, rows: list[Any], writes: list[Any]) -> None:
        self._rows = rows
        self._writes = writes

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def scalars(self, _query) -> FakeScalarResult:
        return FakeScalarResult(self._rows)

    def add(self, row) -> None:
        self._writes.append(row)

    def merge(self, row):
        self._writes.append(row)
        return row

    def commit(self) -> None:
        return None


def test_provider_health_dashboard_job_aggregates_and_persists_snapshots() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    rows = [
        Job(
            job_name="equity_ohlcv_ingestion",
            run_id="run-1",
            status="completed",
            started_at=now - timedelta(minutes=30),
            duration_ms=1200,
            details={"provider": "finnhub"},
        ),
        Job(
            job_name="equity_ohlcv_ingestion",
            run_id="run-2",
            status="failed",
            started_at=now - timedelta(minutes=20),
            duration_ms=1800,
            details={"provider": "finnhub"},
        ),
        Job(
            job_name="crypto_ohlcv_ingestion",
            run_id="run-3",
            status="completed",
            started_at=now - timedelta(minutes=10),
            duration_ms=900,
            details={"provider": "coingecko"},
        ),
        Job(
            job_name="symbol_metadata_ingestion",
            run_id="run-4",
            status="completed",
            started_at=now - timedelta(minutes=5),
            duration_ms=300,
            details={},
        ),
    ]
    persisted: list[Any] = []

    def _factory() -> FakeSession:
        return FakeSession(rows, persisted)

    job = ProviderHealthDashboardJob(
        _factory,
        lookback_hours=4,
        sample_limit=50,
    )
    result = job.run(now_utc=now)

    assert result.provider_count == 2
    snapshots = {snapshot.provider_name: snapshot for snapshot in result.providers}
    assert snapshots["finnhub"].runs_total == 2
    assert snapshots["finnhub"].runs_succeeded == 1
    assert snapshots["finnhub"].runs_failed == 1
    assert snapshots["finnhub"].avg_latency_ms == 1500
    assert snapshots["finnhub"].success_rate == Decimal("50.00")
    assert snapshots["coingecko"].runs_total == 1
    assert snapshots["coingecko"].success_rate == Decimal("100.00")

    provider_health_rows = [row for row in persisted if isinstance(row, ProviderHealth)]
    assert len(provider_health_rows) == 2


def test_run_provider_health_dashboard_updates_audit_details() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    job_rows = [
        Job(
            job_name="macro_ohlcv_ingestion",
            run_id="run-av-1",
            status="completed",
            started_at=now - timedelta(minutes=10),
            duration_ms=1100,
            details={"provider": "alpha_vantage"},
        )
    ]

    def _fetch(_window_start: datetime, _sample_limit: int) -> list[Job]:
        return job_rows

    persisted: list[Any] = []

    def _persist(_snapshot_ts: datetime, snapshots) -> None:
        persisted.extend(snapshots)

    audit_store: dict[str, Any] = {}

    def _audit_factory() -> FakeSession:
        return FakeSession([], [audit_store])

    class AuditCaptureSession:
        def __init__(self, store: dict[str, Any]) -> None:
            self._store = store

        def __enter__(self) -> "AuditCaptureSession":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def add(self, job_row) -> None:
            self._store[job_row.run_id] = job_row

        def merge(self, job_row):
            self._store[job_row.run_id] = job_row
            return job_row

        def commit(self) -> None:
            return None

    def _audit_session_factory() -> AuditCaptureSession:
        return AuditCaptureSession(audit_store)

    audit_trail = JobAuditTrail(_audit_session_factory)

    result = run_provider_health_dashboard(
        settings=Settings(
            provider_health_lookback_hours=12,
            provider_health_job_sample_limit=200,
            provider_health_dashboard_history_limit=24,
        ),
        session_factory=_audit_factory,
        audit_trail=audit_trail,
        now_utc=now,
        fetch_job_rows=_fetch,
        persist_snapshots=_persist,
    )

    assert result.provider_count == 1
    assert len(persisted) == 1

    audit_rows = list(audit_store.values())
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row.job_name == "provider_health_dashboard"
    assert row.status == "completed"
    assert row.details["provider_count"] == 1
    assert row.details["providers"] == ["alpha_vantage"]


def test_read_provider_health_dashboard_shapes_latest_and_history() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    rows = [
        ProviderHealth(
            provider_name="finnhub",
            ts=now - timedelta(minutes=20),
            latency_ms=1500,
            success_rate=Decimal("90.00"),
            quota_remaining=None,
            error_count=1,
        ),
        ProviderHealth(
            provider_name="finnhub",
            ts=now - timedelta(minutes=5),
            latency_ms=1300,
            success_rate=Decimal("95.00"),
            quota_remaining=None,
            error_count=0,
        ),
        ProviderHealth(
            provider_name="coingecko",
            ts=now - timedelta(minutes=7),
            latency_ms=900,
            success_rate=Decimal("100.00"),
            quota_remaining=None,
            error_count=0,
        ),
    ]

    def _factory() -> FakeSession:
        return FakeSession(rows, [])

    payload = read_provider_health_dashboard(
        _factory,
        lookback_hours=6,
        history_limit=2,
        now_utc=now,
    )

    assert payload["status"] == "ok"
    assert payload["provider_count"] == 2
    by_provider = {item["provider_name"]: item for item in payload["providers"]}
    assert by_provider["finnhub"]["latest"]["latency_ms"] == 1300
    assert by_provider["finnhub"]["latest"]["success_rate"] == 95.0
    assert len(by_provider["finnhub"]["history"]) == 2
    assert by_provider["coingecko"]["latest"]["success_rate"] == 100.0
