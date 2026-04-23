"""Provider latency and success dashboard workflows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Job, ProviderHealth
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.provider_health_dashboard")


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    """Aggregated provider metrics for one dashboard snapshot timestamp."""

    provider_name: str
    runs_total: int
    runs_succeeded: int
    runs_failed: int
    avg_latency_ms: int | None
    success_rate: Decimal
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class ProviderHealthDashboardResult:
    """Result summary for one provider-health dashboard refresh run."""

    lookback_hours: int
    sample_limit: int
    providers: list[ProviderHealthSnapshot]

    @property
    def provider_count(self) -> int:
        """Number of providers included in this refresh run."""

        return len(self.providers)


FetchJobRows = Callable[[datetime, int], list[Job]]
PersistSnapshots = Callable[[datetime, list[ProviderHealthSnapshot]], None]


class ProviderHealthDashboardJob:
    """Build and persist provider latency/success snapshots."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        lookback_hours: int,
        sample_limit: int,
        fetch_job_rows: FetchJobRows | None = None,
        persist_snapshots: PersistSnapshots | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._lookback_hours = max(1, lookback_hours)
        self._sample_limit = max(1, sample_limit)
        self._fetch_job_rows = fetch_job_rows or self._default_fetch_job_rows
        self._persist_snapshots = persist_snapshots or self._default_persist_snapshots

    def run(self, *, now_utc: datetime | None = None) -> ProviderHealthDashboardResult:
        """Compute provider metrics from recent job runs and persist snapshots."""

        window_end = normalize_to_utc(now_utc or datetime.now(UTC))
        window_start = window_end - timedelta(hours=self._lookback_hours)
        job_rows = self._fetch_job_rows(window_start, self._sample_limit)
        snapshots = _build_provider_snapshots(
            job_rows, window_start=window_start, window_end=window_end
        )
        self._persist_snapshots(window_end, snapshots)
        return ProviderHealthDashboardResult(
            lookback_hours=self._lookback_hours,
            sample_limit=self._sample_limit,
            providers=snapshots,
        )

    def _default_fetch_job_rows(self, window_start: datetime, sample_limit: int) -> list[Job]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Job)
                    .where(Job.started_at >= window_start)
                    .order_by(Job.started_at.desc())
                    .limit(sample_limit)
                ).all()
            )

    def _default_persist_snapshots(
        self,
        snapshot_ts: datetime,
        snapshots: list[ProviderHealthSnapshot],
    ) -> None:
        if not snapshots:
            return

        with self._session_factory() as session:
            for snapshot in snapshots:
                session.add(
                    ProviderHealth(
                        provider_name=snapshot.provider_name,
                        ts=snapshot_ts,
                        latency_ms=snapshot.avg_latency_ms,
                        success_rate=snapshot.success_rate,
                        quota_remaining=None,
                        error_count=snapshot.runs_failed,
                        details={
                            "runs_total": snapshot.runs_total,
                            "runs_succeeded": snapshot.runs_succeeded,
                            "runs_failed": snapshot.runs_failed,
                            "window_start": snapshot.window_start.isoformat(),
                            "window_end": snapshot.window_end.isoformat(),
                        },
                    )
                )
            session.commit()


def run_provider_health_dashboard(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
    fetch_job_rows: FetchJobRows | None = None,
    persist_snapshots: PersistSnapshots | None = None,
) -> ProviderHealthDashboardResult:
    """Run provider-health dashboard refresh with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)

    job = ProviderHealthDashboardJob(
        resolved_session_factory,
        lookback_hours=resolved_settings.provider_health_lookback_hours,
        sample_limit=resolved_settings.provider_health_job_sample_limit,
        fetch_job_rows=fetch_job_rows,
        persist_snapshots=persist_snapshots,
    )
    with resolved_audit.track_job_run(
        "provider_health_dashboard",
        details={
            "lookback_hours": resolved_settings.provider_health_lookback_hours,
            "sample_limit": resolved_settings.provider_health_job_sample_limit,
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "provider_count": result.provider_count,
                "providers": [snapshot.provider_name for snapshot in result.providers],
            }
        )
        return result


def read_provider_health_dashboard(
    session_factory: SessionFactory,
    *,
    lookback_hours: int,
    history_limit: int,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Read provider-health dashboard data for API consumption."""

    window_end = normalize_to_utc(now_utc or datetime.now(UTC))
    window_start = window_end - timedelta(hours=max(1, lookback_hours))
    max_points = max(1, history_limit)

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ProviderHealth)
                .where(ProviderHealth.ts >= window_start)
                .order_by(ProviderHealth.provider_name.asc(), ProviderHealth.ts.asc())
            ).all()
        )

    grouped: dict[str, list[ProviderHealth]] = defaultdict(list)
    for row in rows:
        grouped[row.provider_name].append(row)

    providers_payload: list[dict[str, Any]] = []
    for provider_name in sorted(grouped):
        history_rows = grouped[provider_name][-max_points:]
        latest = history_rows[-1]
        providers_payload.append(
            {
                "provider_name": provider_name,
                "latest": {
                    "ts": normalize_to_utc(latest.ts).isoformat(),
                    "latency_ms": latest.latency_ms,
                    "success_rate": _decimal_to_float(latest.success_rate),
                    "error_count": latest.error_count,
                },
                "history": [
                    {
                        "ts": normalize_to_utc(item.ts).isoformat(),
                        "latency_ms": item.latency_ms,
                        "success_rate": _decimal_to_float(item.success_rate),
                        "error_count": item.error_count,
                    }
                    for item in history_rows
                ],
            }
        )

    return {
        "status": "ok",
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "provider_count": len(providers_payload),
        "providers": providers_payload,
    }


def _build_provider_snapshots(
    job_rows: list[Job],
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[ProviderHealthSnapshot]:
    grouped: dict[str, list[Job]] = defaultdict(list)
    for row in job_rows:
        provider_name = _extract_provider_name(row)
        if provider_name is None:
            continue
        if row.status not in {"completed", "failed"}:
            continue
        grouped[provider_name].append(row)

    snapshots: list[ProviderHealthSnapshot] = []
    for provider_name in sorted(grouped):
        rows = grouped[provider_name]
        runs_total = len(rows)
        runs_succeeded = sum(1 for row in rows if row.status == "completed")
        runs_failed = runs_total - runs_succeeded

        latencies = [row.duration_ms for row in rows if row.duration_ms is not None]
        avg_latency = int(round(sum(latencies) / len(latencies))) if latencies else None
        success_rate = _build_success_rate(runs_succeeded, runs_total)

        snapshots.append(
            ProviderHealthSnapshot(
                provider_name=provider_name,
                runs_total=runs_total,
                runs_succeeded=runs_succeeded,
                runs_failed=runs_failed,
                avg_latency_ms=avg_latency,
                success_rate=success_rate,
                window_start=window_start,
                window_end=window_end,
            )
        )
    return snapshots


def _extract_provider_name(job_row: Job) -> str | None:
    details = job_row.details
    if not isinstance(details, dict):
        return None
    provider = details.get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip().lower()
    return None


def _build_success_rate(succeeded: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    value = (Decimal(succeeded) / Decimal(total)) * Decimal("100")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    """CLI entrypoint for provider dashboard refresh."""

    result = run_provider_health_dashboard()
    logger.info(
        "provider_health_dashboard_completed",
        extra={
            "provider_count": result.provider_count,
            "providers": [snapshot.provider_name for snapshot in result.providers],
            "lookback_hours": result.lookback_hours,
            "sample_limit": result.sample_limit,
        },
    )
    print(
        "provider_health_dashboard:"
        f" provider_count={result.provider_count}"
        f" providers={','.join(snapshot.provider_name for snapshot in result.providers)}"
        f" lookback_hours={result.lookback_hours}"
        f" sample_limit={result.sample_limit}"
    )


if __name__ == "__main__":
    main()
