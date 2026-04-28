"""Small TTL response cache for high-frequency dashboard queries.

This is intentionally lightweight (in-memory) to keep the personal stack simple.
If the app is ever deployed as multiple API workers, replace this with Redis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    expires_at_epoch: float
    value: object


class ApiResponseCache:
    """Thread-safe in-memory TTL cache with a soft max size."""

    def __init__(self, *, max_entries: int) -> None:
        self._max_entries = max(100, max_entries)
        self._lock = Lock()
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> object | None:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at_epoch <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, *, value: object, ttl_seconds: int) -> None:
        ttl = max(1, int(ttl_seconds))
        expires_at = time.time() + ttl
        with self._lock:
            self._entries[key] = CacheEntry(expires_at_epoch=expires_at, value=value)
            self._evict_if_needed_locked()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            expired = sum(1 for entry in self._entries.values() if entry.expires_at_epoch <= now)
            return {
                "entries": len(self._entries),
                "expired": expired,
                "max_entries": self._max_entries,
            }

    def _evict_if_needed_locked(self) -> None:
        if len(self._entries) <= self._max_entries:
            return

        now = time.time()
        keys_sorted = sorted(
            self._entries.items(),
            key=lambda kv: (kv[1].expires_at_epoch <= now, kv[1].expires_at_epoch),
        )
        # Evict ~10% at a time to avoid constant churn when under heavy load.
        target = max(1, int(self._max_entries * 0.1))
        for key, _entry in keys_sorted[:target]:
            self._entries.pop(key, None)
