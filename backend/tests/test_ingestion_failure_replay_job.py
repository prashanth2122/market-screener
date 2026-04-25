"""Tests for manual ingestion failure replay tool (Day 82)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.db.models.core import Asset, IngestionFailure, Job, Price
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.ingestion_replay import run_ingestion_failure_replay


def test_ingestion_failure_replay_retries_failures_in_window(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    Job.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    with session_local() as session:
        session.add(
            Asset(
                symbol="AAPL",
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            IngestionFailure(
                failure_key="failure-replay-1",
                job_name="equity_ohlcv_ingestion",
                asset_symbol="AAPL",
                provider_name="finnhub",
                status="pending",
                attempt_count=1,
                error_message="provider outage",
                context={
                    "resolution": "D",
                    "lookback_days": 365,
                    "from_unix": 1704067200,
                    "to_unix": 1704153600,
                },
                first_seen_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(hours=2),
                next_retry_at=now - timedelta(hours=1),
            )
        )
        session.commit()

    class MockFinnhub:
        def __enter__(self) -> "MockFinnhub":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_stock_candles(
            self,
            symbol: str,
            *,
            resolution: str,
            from_unix: int,
            to_unix: int,
        ) -> dict[str, Any]:
            assert symbol == "AAPL"
            assert resolution == "D"
            assert from_unix < to_unix
            return {
                "s": "ok",
                "t": [1704067200],
                "o": [100.0],
                "h": [101.0],
                "l": [99.0],
                "c": [100.5],
                "v": [1000.0],
            }

    monkeypatch.setattr(
        "market_screener.jobs.ingestion_replay.FinnhubClient.from_settings",
        lambda _settings: MockFinnhub(),
    )

    store = IngestionFailureStore(
        session_local,
        max_attempts=5,
        retry_backoff_minutes="1,2,3",
    )
    result = run_ingestion_failure_replay(
        session_factory=session_local,
        failure_store=store,
        now_utc=now,
        since_hours=6,
        until_hours=0,
        limit=10,
        job_name="equity_ohlcv_ingestion",
        statuses={"pending"},
    )

    assert result.selected_failures == 1
    assert result.attempted == 1
    assert result.retried_success == 1

    with session_local() as session:
        failure_row = session.scalar(select(IngestionFailure))
        price_rows = session.scalars(select(Price)).all()

    assert failure_row is not None
    assert failure_row.status == "resolved"
    assert len(price_rows) == 1


def test_ingestion_failure_replay_respects_window_filter(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    Job.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    with session_local() as session:
        session.add(
            Asset(
                symbol="AAPL",
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            IngestionFailure(
                failure_key="failure-old",
                job_name="equity_ohlcv_ingestion",
                asset_symbol="AAPL",
                provider_name="finnhub",
                status="pending",
                attempt_count=1,
                error_message="provider outage",
                context={},
                first_seen_at=now - timedelta(days=5),
                last_seen_at=now - timedelta(days=5),
                next_retry_at=None,
            )
        )
        session.commit()

    class MockFinnhub:
        def __enter__(self) -> "MockFinnhub":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_stock_candles(self, symbol: str, *, resolution: str, from_unix: int, to_unix: int):
            raise AssertionError("Should not be called for out-of-window failure")

    monkeypatch.setattr(
        "market_screener.jobs.ingestion_replay.FinnhubClient.from_settings",
        lambda _settings: MockFinnhub(),
    )

    store = IngestionFailureStore(
        session_local,
        max_attempts=5,
        retry_backoff_minutes="1,2,3",
    )
    result = run_ingestion_failure_replay(
        session_factory=session_local,
        failure_store=store,
        now_utc=now,
        since_hours=24,
        until_hours=0,
        limit=10,
    )

    assert result.selected_failures == 0
    assert result.attempted == 0
