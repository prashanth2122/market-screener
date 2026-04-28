"""Slow query profiling for SQLAlchemy engines.

Goal: make it easy to spot unexpectedly slow DB queries during local use and soak tests,
without adding a heavy APM dependency.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import Engine, event

logger = logging.getLogger("market_screener.db.slow_queries")

_ENGINE_PROFILERS: "WeakKeyDictionary[Engine, SlowQueryProfiler]" = WeakKeyDictionary()


@dataclass(frozen=True)
class SlowQueryEvent:
    recorded_at_epoch: float
    duration_ms: float
    statement: str
    params_repr: str
    rowcount: int | None


class SlowQueryProfiler:
    """In-memory ring buffer for slow query events."""

    def __init__(
        self,
        *,
        threshold_ms: int,
        max_entries: int,
        max_sql_chars: int,
    ) -> None:
        self._threshold_ms = max(1, int(threshold_ms))
        self._max_sql_chars = max(200, int(max_sql_chars))
        self._events: deque[SlowQueryEvent] = deque(maxlen=max(10, int(max_entries)))

    @property
    def threshold_ms(self) -> int:
        return self._threshold_ms

    def record(
        self,
        *,
        duration_ms: float,
        statement: str,
        parameters: Any,
        rowcount: int | None,
    ) -> None:
        if duration_ms < self._threshold_ms:
            return

        sql = " ".join(str(statement or "").split())
        if len(sql) > self._max_sql_chars:
            sql = sql[: self._max_sql_chars] + "...(truncated)"

        params_repr = _safe_params_repr(parameters)
        event_row = SlowQueryEvent(
            recorded_at_epoch=time.time(),
            duration_ms=float(duration_ms),
            statement=sql,
            params_repr=params_repr,
            rowcount=rowcount,
        )
        self._events.appendleft(event_row)

        logger.warning(
            "db_slow_query",
            extra={
                "duration_ms": round(duration_ms, 2),
                "threshold_ms": self._threshold_ms,
                "rowcount": rowcount,
                "statement": sql,
            },
        )

    def snapshot(self, *, limit: int) -> list[SlowQueryEvent]:
        limited = max(1, int(limit))
        return list(self._events)[:limited]

    def stats(self) -> dict[str, object]:
        return {
            "threshold_ms": self._threshold_ms,
            "max_entries": self._events.maxlen,
            "stored": len(self._events),
        }


def install_slow_query_profiler(
    engine: Engine,
    *,
    threshold_ms: int,
    max_entries: int,
    max_sql_chars: int,
) -> SlowQueryProfiler:
    """Attach slow query profiler to an engine (idempotent)."""

    existing = _ENGINE_PROFILERS.get(engine)
    if existing is not None:
        return existing

    profiler = SlowQueryProfiler(
        threshold_ms=threshold_ms,
        max_entries=max_entries,
        max_sql_chars=max_sql_chars,
    )
    _ENGINE_PROFILERS[engine] = profiler

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started_list = conn.info.get("_query_start_time")
        if not started_list:
            return
        started = started_list.pop()
        duration_ms = (time.perf_counter() - started) * 1000.0
        profiler.record(
            duration_ms=duration_ms,
            statement=statement,
            parameters=parameters,
            rowcount=getattr(cursor, "rowcount", None),
        )

    return profiler


def get_slow_query_profiler(engine: Engine) -> SlowQueryProfiler | None:
    return _ENGINE_PROFILERS.get(engine)


def _safe_params_repr(parameters: Any) -> str:
    try:
        if parameters is None:
            return "none"
        if isinstance(parameters, (list, tuple)):
            return f"seq(len={len(parameters)})"
        if isinstance(parameters, dict):
            keys = list(parameters.keys())
            keys.sort()
            return f"dict(keys={keys[:10]})"
        return type(parameters).__name__
    except Exception:
        return "unavailable"
