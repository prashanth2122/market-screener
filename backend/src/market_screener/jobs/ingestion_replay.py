"""Manual replay tool for ingestion failures in a time window (Day 82)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from market_screener.core.settings import Settings, get_settings
from market_screener.db.session import (
    SessionFactory,
    create_session_factory_from_settings,
)
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.ingestion_retry import IngestionFailureRetryJob
from market_screener.providers.finnhub import FinnhubClient

logger = logging.getLogger("market_screener.jobs.ingestion_replay")


@dataclass(frozen=True)
class IngestionReplayResult:
    """Summary of one replay pass over selected failures."""

    selected_failures: int
    attempted: int
    retried_success: int
    retried_no_data: int
    retry_failed: int
    dead_lettered: int
    since_utc: datetime
    until_utc: datetime
    job_name: str | None
    statuses: list[str]


def run_ingestion_failure_replay(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    failure_store: IngestionFailureStore | None = None,
    now_utc: datetime | None = None,
    since_hours: int = 24,
    until_hours: int = 0,
    limit: int = 200,
    job_name: str | None = None,
    statuses: set[str] | None = None,
) -> IngestionReplayResult:
    """Replay failures for a specific failure window."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    resolved_failure_store = failure_store or IngestionFailureStore(
        resolved_session_factory,
        max_attempts=resolved_settings.ingestion_failure_max_attempts,
        retry_backoff_minutes=resolved_settings.ingestion_failure_retry_backoff_minutes,
    )

    reference_now = now_utc or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)

    normalized_since = max(0, int(since_hours))
    normalized_until = max(0, int(until_hours))
    since_utc = reference_now - timedelta(hours=normalized_since)
    until_utc = reference_now - timedelta(hours=normalized_until)
    if until_utc < since_utc:
        since_utc, until_utc = until_utc, since_utc

    normalized_limit = max(1, min(int(limit), 1000))
    failures = resolved_failure_store.fetch_failures_for_replay(
        limit=normalized_limit,
        since_utc=since_utc,
        until_utc=until_utc,
        job_name=job_name,
        statuses=statuses,
    )

    def _client_factory() -> FinnhubClient:
        return FinnhubClient.from_settings(resolved_settings)

    retry_job = IngestionFailureRetryJob(
        resolved_session_factory,
        resolved_failure_store,
        _client_factory,
        default_resolution=resolved_settings.equity_ohlcv_resolution,
        default_lookback_days=resolved_settings.equity_ohlcv_lookback_days,
        batch_size=1,
    )

    attempted = 0
    retried_success = 0
    retried_no_data = 0
    retry_failed = 0
    dead_lettered = 0

    with resolved_audit.track_job_run(
        "ingestion_failure_replay",
        details={
            "since_utc": since_utc.isoformat(),
            "until_utc": until_utc.isoformat(),
            "limit": normalized_limit,
            "job_name": (job_name or "").strip() or None,
            "statuses": sorted(statuses or {"pending", "retrying"}),
        },
    ) as run_handle:
        with _client_factory() as client:
            for failure in failures:
                attempted += 1
                outcome = retry_job._retry_one_failure(failure, client)  # type: ignore[attr-defined]
                if outcome == "success":
                    retried_success += 1
                elif outcome == "no_data":
                    retried_no_data += 1
                elif outcome == "dead":
                    dead_lettered += 1
                else:
                    retry_failed += 1

        run_handle.add_details(
            {
                "selected_failures": len(failures),
                "attempted": attempted,
                "retried_success": retried_success,
                "retried_no_data": retried_no_data,
                "retry_failed": retry_failed,
                "dead_lettered": dead_lettered,
            }
        )

    return IngestionReplayResult(
        selected_failures=len(failures),
        attempted=attempted,
        retried_success=retried_success,
        retried_no_data=retried_no_data,
        retry_failed=retry_failed,
        dead_lettered=dead_lettered,
        since_utc=since_utc,
        until_utc=until_utc,
        job_name=(job_name or "").strip() or None,
        statuses=sorted(statuses or {"pending", "retrying"}),
    )


def main() -> None:
    """CLI entrypoint for manual ingestion failure replay."""

    result = run_ingestion_failure_replay()
    logger.info(
        "ingestion_failure_replay_completed",
        extra={
            "selected_failures": result.selected_failures,
            "attempted": result.attempted,
            "retried_success": result.retried_success,
            "retried_no_data": result.retried_no_data,
            "retry_failed": result.retry_failed,
            "dead_lettered": result.dead_lettered,
            "since_utc": result.since_utc.isoformat(),
            "until_utc": result.until_utc.isoformat(),
        },
    )
    print(
        "ingestion_failure_replay:"
        f" selected_failures={result.selected_failures}"
        f" attempted={result.attempted}"
        f" retried_success={result.retried_success}"
        f" retried_no_data={result.retried_no_data}"
        f" retry_failed={result.retry_failed}"
        f" dead_lettered={result.dead_lettered}"
        f" since_utc={result.since_utc.isoformat()}"
        f" until_utc={result.until_utc.isoformat()}"
    )


if __name__ == "__main__":
    main()
