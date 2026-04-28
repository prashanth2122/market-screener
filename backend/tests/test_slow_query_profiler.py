"""Tests for the SQLAlchemy slow query profiler."""

from __future__ import annotations

import time

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from market_screener.db.slow_query_profiler import (
    get_slow_query_profiler,
    install_slow_query_profiler,
)


def test_profiler_records_slow_query_via_engine_events() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    profiler = install_slow_query_profiler(
        engine,
        threshold_ms=5,
        max_entries=50,
        max_sql_chars=300,
    )

    # Register a deterministic sleep function so we can force a slow query.
    raw = engine.raw_connection()
    raw.driver_connection.create_function("sleep_ms", 1, lambda ms: time.sleep(float(ms) / 1000.0))
    raw.close()

    with engine.connect() as conn:
        conn.execute(text("SELECT sleep_ms(25)"))

    snapshot = profiler.snapshot(limit=10)
    assert snapshot
    assert any(item.duration_ms >= 5 for item in snapshot)

    attached = get_slow_query_profiler(engine)
    assert attached is profiler
