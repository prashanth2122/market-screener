"""Ingestion failure persistence and retry state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from market_screener.db.models.core import IngestionFailure
from market_screener.db.session import SessionFactory


@dataclass(frozen=True)
class IngestionFailureItem:
    """Immutable failure row snapshot used by retry workers."""

    id: int
    failure_key: str
    job_name: str
    asset_symbol: str | None
    provider_name: str | None
    status: str
    attempt_count: int
    error_message: str
    context: dict[str, Any]
    next_retry_at: datetime | None


class IngestionFailureStore:
    """Persistence interface for ingestion failures and retry state transitions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        max_attempts: int,
        retry_backoff_minutes: str,
    ) -> None:
        self._session_factory = session_factory
        self._max_attempts = max(1, max_attempts)
        self._retry_schedule = _parse_retry_schedule(retry_backoff_minutes)

    def record_failure(
        self,
        *,
        failure_key: str,
        job_name: str,
        asset_symbol: str | None,
        provider_name: str | None,
        error_message: str,
        context: dict[str, Any] | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        """Insert or update a failure row keyed by deterministic failure key."""

        now = now_utc or datetime.now(UTC)
        safe_message = error_message[:1000]
        safe_context = dict(context or {})

        with self._session_factory() as session:
            row = session.scalar(
                select(IngestionFailure).where(IngestionFailure.failure_key == failure_key)
            )

            if row is None:
                row = IngestionFailure(
                    failure_key=failure_key,
                    job_name=job_name,
                    asset_symbol=asset_symbol,
                    provider_name=provider_name,
                    status="pending",
                    attempt_count=1,
                    error_message=safe_message,
                    context=safe_context,
                    first_seen_at=now,
                    last_seen_at=now,
                    next_retry_at=now + timedelta(minutes=self._retry_delay_minutes(1)),
                )
                session.add(row)
                session.commit()
                return

            row.attempt_count += 1
            row.last_seen_at = now
            row.error_message = safe_message
            row.context = safe_context
            if row.attempt_count >= self._max_attempts:
                row.status = "dead"
                row.next_retry_at = None
                row.resolved_at = now
            else:
                row.status = "retrying"
                row.resolved_at = None
                row.next_retry_at = now + timedelta(
                    minutes=self._retry_delay_minutes(row.attempt_count)
                )
            session.commit()

    def fetch_due_failures(
        self,
        *,
        limit: int,
        now_utc: datetime | None = None,
    ) -> list[IngestionFailureItem]:
        """Fetch due failures in retry order."""

        now = now_utc or datetime.now(UTC)
        with self._session_factory() as session:
            rows = session.scalars(
                select(IngestionFailure)
                .where(
                    IngestionFailure.status.in_(("pending", "retrying")),
                    IngestionFailure.next_retry_at.is_not(None),
                    IngestionFailure.next_retry_at <= now,
                )
                .order_by(IngestionFailure.next_retry_at.asc(), IngestionFailure.id.asc())
                .limit(limit)
            ).all()

        return [
            IngestionFailureItem(
                id=row.id,
                failure_key=row.failure_key,
                job_name=row.job_name,
                asset_symbol=row.asset_symbol,
                provider_name=row.provider_name,
                status=row.status,
                attempt_count=row.attempt_count,
                error_message=row.error_message,
                context=dict(row.context or {}),
                next_retry_at=row.next_retry_at,
            )
            for row in rows
        ]

    def fetch_failures_for_replay(
        self,
        *,
        limit: int,
        since_utc: datetime,
        until_utc: datetime,
        job_name: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[IngestionFailureItem]:
        """Fetch failures for a specific time window, ignoring next_retry schedule."""

        normalized_job = (job_name or "").strip() or None
        allowed_statuses = {status.strip() for status in (statuses or set()) if status.strip()}
        if not allowed_statuses:
            allowed_statuses = {"pending", "retrying"}

        with self._session_factory() as session:
            query = select(IngestionFailure).where(
                IngestionFailure.last_seen_at >= since_utc,
                IngestionFailure.last_seen_at <= until_utc,
                IngestionFailure.status.in_(tuple(sorted(allowed_statuses))),
            )
            if normalized_job:
                query = query.where(IngestionFailure.job_name == normalized_job)
            rows = session.scalars(
                query.order_by(
                    IngestionFailure.last_seen_at.desc(), IngestionFailure.id.desc()
                ).limit(limit)
            ).all()

        return [
            IngestionFailureItem(
                id=row.id,
                failure_key=row.failure_key,
                job_name=row.job_name,
                asset_symbol=row.asset_symbol,
                provider_name=row.provider_name,
                status=row.status,
                attempt_count=row.attempt_count,
                error_message=row.error_message,
                context=dict(row.context or {}),
                next_retry_at=row.next_retry_at,
            )
            for row in rows
        ]

    def mark_resolved(
        self,
        failure_id: int,
        *,
        resolution_context: dict[str, Any] | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        """Mark failure as resolved after successful replay or benign no-data retry."""

        now = now_utc or datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(select(IngestionFailure).where(IngestionFailure.id == failure_id))
            if row is None:
                return
            merged_context = dict(row.context or {})
            merged_context.update(resolution_context or {})
            row.status = "resolved"
            row.resolved_at = now
            row.next_retry_at = None
            row.context = merged_context
            session.commit()

    def mark_dead(
        self,
        failure_id: int,
        *,
        reason: str,
        now_utc: datetime | None = None,
    ) -> None:
        """Mark a failure as dead-lettered when retrying is no longer useful."""

        now = now_utc or datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(select(IngestionFailure).where(IngestionFailure.id == failure_id))
            if row is None:
                return
            merged_context = dict(row.context or {})
            merged_context["dead_reason"] = reason
            row.status = "dead"
            row.resolved_at = now
            row.next_retry_at = None
            row.context = merged_context
            session.commit()

    def register_retry_failure(
        self,
        failure_id: int,
        *,
        error_message: str,
        now_utc: datetime | None = None,
    ) -> bool:
        """Register a retry failure; returns true when item is dead-lettered."""

        now = now_utc or datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(select(IngestionFailure).where(IngestionFailure.id == failure_id))
            if row is None:
                return False

            row.attempt_count += 1
            row.last_seen_at = now
            row.error_message = error_message[:1000]
            if row.attempt_count >= self._max_attempts:
                row.status = "dead"
                row.next_retry_at = None
                row.resolved_at = now
                session.commit()
                return True

            row.status = "retrying"
            row.next_retry_at = now + timedelta(
                minutes=self._retry_delay_minutes(row.attempt_count)
            )
            session.commit()
            return False

    def _retry_delay_minutes(self, attempt_count: int) -> int:
        index = min(max(attempt_count, 1) - 1, len(self._retry_schedule) - 1)
        return self._retry_schedule[index]


def _parse_retry_schedule(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        values.append(max(1, int(cleaned)))
    if not values:
        return [5]
    return values
