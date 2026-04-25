"""Alert history API endpoint backed by dispatch job audit logs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Job
from market_screener.db.session import SessionFactory, create_session_factory_from_settings

router = APIRouter(tags=["alerts"])

_CHANNEL_BY_JOB_NAME = {
    "email_alert_dispatch": "email",
    "telegram_alert_dispatch": "telegram",
}


@router.get("/history")
def get_alert_history(
    channel: str | None = Query(default=None, pattern="^(email|telegram)$"),
    symbol: str | None = Query(default=None),
    since_hours: int = Query(default=168, ge=1, le=24 * 365),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return sent alert history events from dispatch job audit records."""

    normalized_channel = (channel or "").strip().lower() or None
    normalized_symbol = (symbol or "").strip().upper() or None
    session_factory = create_session_factory_from_settings(settings)
    events = _read_alert_history_events(
        session_factory,
        since_hours=since_hours,
    )

    if normalized_channel:
        events = [event for event in events if event["channel"] == normalized_channel]
    if normalized_symbol:
        events = [event for event in events if event["symbol"] == normalized_symbol]

    total = len(events)
    page = events[offset : offset + limit]
    return {
        "status": "ok",
        "filters": {
            "channel": normalized_channel,
            "symbol": normalized_symbol,
            "since_hours": since_hours,
        },
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned": len(page),
        },
        "items": page,
    }


def _read_alert_history_events(
    session_factory: SessionFactory,
    *,
    since_hours: int,
    now_utc: datetime | None = None,
) -> list[dict[str, object]]:
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    cutoff = reference_now - timedelta(hours=since_hours)

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(Job)
                .where(
                    Job.job_name.in_(tuple(_CHANNEL_BY_JOB_NAME.keys())),
                    Job.started_at >= cutoff,
                )
                .order_by(Job.started_at.desc())
            ).all()
        )

    event_rows: list[tuple[datetime, dict[str, object]]] = []
    for row in rows:
        channel = _CHANNEL_BY_JOB_NAME.get(row.job_name)
        if channel is None:
            continue

        details = row.details if isinstance(row.details, dict) else {}
        sent_alerts = details.get("sent_alerts")
        if not isinstance(sent_alerts, list):
            continue

        for index, item in enumerate(sent_alerts):
            if not isinstance(item, dict):
                continue
            symbol_value = item.get("symbol")
            if not isinstance(symbol_value, str) or not symbol_value.strip():
                continue
            normalized_symbol = symbol_value.strip().upper()
            sent_at = _parse_optional_datetime(item.get("sent_at"), fallback=row.started_at)
            as_of_ts = _parse_optional_datetime(item.get("as_of_ts"), fallback=None)
            payload = {
                "id": f"{row.run_id}:{index}",
                "run_id": row.run_id,
                "channel": channel,
                "symbol": normalized_symbol,
                "status": row.status,
                "as_of_ts": None if as_of_ts is None else as_of_ts.isoformat(),
                "sent_at": sent_at.isoformat(),
                "job_started_at": normalize_to_utc(row.started_at).isoformat(),
                "job_finished_at": (
                    None
                    if row.finished_at is None
                    else normalize_to_utc(row.finished_at).isoformat()
                ),
            }
            event_rows.append((sent_at, payload))

    event_rows.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in event_rows]


def _parse_optional_datetime(value: object, *, fallback: datetime | None) -> datetime | None:
    if isinstance(value, str) and value.strip():
        try:
            return normalize_to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            pass
    if fallback is None:
        return None
    return normalize_to_utc(fallback)
