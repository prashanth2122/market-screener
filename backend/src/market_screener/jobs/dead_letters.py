"""Dead-letter queue persistence for non-retryable ingestion payload failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from market_screener.db.models.core import DeadLetterPayload
from market_screener.db.session import SessionFactory


@dataclass(frozen=True)
class DeadLetterPayloadItem:
    """Immutable dead-letter row snapshot (used mainly for tests and tooling)."""

    id: int
    dead_letter_key: str
    job_name: str
    asset_symbol: str | None
    provider_name: str | None
    payload_type: str
    reason: str
    error_message: str
    payload: object | None
    context: dict[str, Any]
    seen_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class DeadLetterStore:
    """Persistence interface for non-retryable ingestion payload failures."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_dead_letter(
        self,
        *,
        dead_letter_key: str,
        job_name: str,
        asset_symbol: str | None,
        provider_name: str | None,
        payload_type: str,
        reason: str,
        error_message: str,
        payload: object | None,
        context: dict[str, Any] | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        """Insert or update a dead-letter row keyed by deterministic key."""

        now = now_utc or datetime.now(UTC)
        safe_message = error_message[:1000]
        safe_context = dict(context or {})

        with self._session_factory() as session:
            row = session.scalar(
                select(DeadLetterPayload).where(
                    DeadLetterPayload.dead_letter_key == dead_letter_key
                )
            )
            if row is None:
                row = DeadLetterPayload(
                    dead_letter_key=dead_letter_key,
                    job_name=job_name,
                    asset_symbol=asset_symbol,
                    provider_name=provider_name,
                    payload_type=payload_type,
                    reason=reason,
                    error_message=safe_message,
                    payload=payload,
                    context=safe_context,
                    seen_count=1,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(row)
                session.commit()
                return

            row.seen_count += 1
            row.last_seen_at = now
            row.error_message = safe_message
            row.reason = reason
            row.payload_type = payload_type
            row.payload = payload
            row.context = safe_context
            session.commit()

    def fetch_recent(
        self,
        *,
        limit: int,
    ) -> list[DeadLetterPayloadItem]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DeadLetterPayload)
                .order_by(DeadLetterPayload.last_seen_at.desc(), DeadLetterPayload.id.desc())
                .limit(max(1, limit))
            ).all()
        return [
            DeadLetterPayloadItem(
                id=row.id,
                dead_letter_key=row.dead_letter_key,
                job_name=row.job_name,
                asset_symbol=row.asset_symbol,
                provider_name=row.provider_name,
                payload_type=row.payload_type,
                reason=row.reason,
                error_message=row.error_message,
                payload=row.payload,
                context=dict(row.context or {}),
                seen_count=row.seen_count,
                first_seen_at=row.first_seen_at,
                last_seen_at=row.last_seen_at,
            )
            for row in rows
        ]
