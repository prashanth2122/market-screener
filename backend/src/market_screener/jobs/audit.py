"""Job audit trail persistence helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from market_screener.db.models.core import Job
from market_screener.db.session import SessionFactory


@dataclass
class JobRunHandle:
    """Mutable run context used while a job execution is in progress."""

    job_name: str
    run_id: str
    started_at: datetime
    idempotency_key: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def add_details(self, extra: dict[str, object]) -> None:
        """Merge additional execution details into run metadata."""

        self.details.update(extra)


class JobAuditTrail:
    """Persist job lifecycle records into the `jobs` audit table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._active_runs: dict[str, Job] = {}
        self._completed_idempotency: set[tuple[str, str]] = set()

    def has_completed_run(self, job_name: str, idempotency_key: str | None) -> bool:
        """Return true when a completed run already exists for this idempotency key."""

        if not idempotency_key:
            return False

        cached_key = (job_name, idempotency_key)
        if cached_key in self._completed_idempotency:
            return True

        with self._session_factory() as session:
            try:
                existing_id = session.scalar(
                    select(Job.id)
                    .where(
                        Job.job_name == job_name,
                        Job.status == "completed",
                        Job.idempotency_key == idempotency_key,
                    )
                    .limit(1)
                )
            except Exception:
                return False

        if existing_id is None:
            return False

        self._completed_idempotency.add(cached_key)
        return True

    @contextmanager
    def track_job_run(
        self,
        job_name: str,
        *,
        details: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> Iterator[JobRunHandle]:
        """Track a job run and persist success/failure outcome automatically."""

        handle = self._start(job_name, details or {}, idempotency_key=idempotency_key)
        try:
            yield handle
        except Exception as exc:
            self._finish_failed(handle, str(exc))
            raise
        else:
            self._finish_completed(handle)

    def _start(
        self,
        job_name: str,
        details: dict[str, object],
        *,
        idempotency_key: str | None,
    ) -> JobRunHandle:
        run_id = uuid4().hex
        started_at = datetime.now(UTC)
        job_row = Job(
            job_name=job_name,
            run_id=run_id,
            idempotency_key=idempotency_key,
            status="running",
            started_at=started_at,
            details=dict(details),
        )
        self._persist_new(job_row)
        self._active_runs[run_id] = job_row
        return JobRunHandle(
            job_name=job_name,
            run_id=run_id,
            started_at=started_at,
            idempotency_key=idempotency_key,
            details=dict(details),
        )

    def _finish_completed(self, handle: JobRunHandle) -> None:
        job_row = self._active_runs.pop(handle.run_id)
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - handle.started_at).total_seconds() * 1000)
        job_row.status = "completed"
        job_row.finished_at = finished_at
        job_row.duration_ms = duration_ms
        job_row.error_message = None
        job_row.details = dict(handle.details)
        self._persist_update(job_row)
        if handle.idempotency_key:
            self._completed_idempotency.add((handle.job_name, handle.idempotency_key))

    def _finish_failed(self, handle: JobRunHandle, error_message: str) -> None:
        job_row = self._active_runs.pop(handle.run_id)
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - handle.started_at).total_seconds() * 1000)
        job_row.status = "failed"
        job_row.finished_at = finished_at
        job_row.duration_ms = duration_ms
        job_row.error_message = error_message[:1000]
        job_row.details = dict(handle.details)
        self._persist_update(job_row)

    def _persist_new(self, job_row: Job) -> None:
        with self._session_factory() as session:
            session.add(job_row)
            session.commit()

    def _persist_update(self, job_row: Job) -> None:
        with self._session_factory() as session:
            session.merge(job_row)
            session.commit()
