"""Timezone helpers for consistent UTC normalization."""

from __future__ import annotations

from datetime import UTC, datetime


def normalize_to_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for storage and comparisons."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_utc_unix_seconds(value: datetime) -> int:
    """Convert a datetime to UTC unix seconds."""

    return int(normalize_to_utc(value).timestamp())
