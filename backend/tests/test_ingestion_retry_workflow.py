"""Tests for ingestion failure table and retry workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, IngestionFailure, Price
from market_screener.jobs.equity_ohlcv import EquityOhlcvIngestionJob
from market_screener.jobs.ingestion_failures import IngestionFailureStore
from market_screener.jobs.ingestion_retry import IngestionFailureRetryJob


def test_equity_ohlcv_job_records_ingestion_failure_on_provider_error() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
            raise RuntimeError("provider outage")

    failure_store = IngestionFailureStore(
        session_local,
        max_attempts=5,
        retry_backoff_minutes="1,2,3",
    )
    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: MockFinnhub(),
        resolution="D",
        lookback_days=365,
        failure_store=failure_store,
    )

    result = job.run()

    assert result.failed_symbols == 1
    with session_local() as session:
        row = session.scalar(select(IngestionFailure))

    assert row is not None
    assert row.job_name == "equity_ohlcv_ingestion"
    assert row.asset_symbol == "AAPL"
    assert row.provider_name == "finnhub"
    assert row.status == "pending"
    assert row.attempt_count == 1
    assert "provider outage" in row.error_message


def test_ingestion_retry_job_replays_due_failure_successfully() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
                failure_key="failure-1",
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
                first_seen_at=datetime.now(UTC) - timedelta(minutes=10),
                last_seen_at=datetime.now(UTC) - timedelta(minutes=10),
                next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
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

    failure_store = IngestionFailureStore(
        session_local,
        max_attempts=5,
        retry_backoff_minutes="1,2,3",
    )
    job = IngestionFailureRetryJob(
        session_local,
        failure_store,
        lambda: MockFinnhub(),
        default_resolution="D",
        default_lookback_days=365,
        batch_size=20,
    )

    result = job.run()

    assert result.due_failures == 1
    assert result.attempted == 1
    assert result.retried_success == 1
    assert result.retry_failed == 0
    assert result.dead_lettered == 0

    with session_local() as session:
        failure_row = session.scalar(select(IngestionFailure))
        price_count = session.scalar(select(func.count()).select_from(Price))

    assert failure_row is not None
    assert failure_row.status == "resolved"
    assert failure_row.resolved_at is not None
    assert price_count == 1


def test_ingestion_retry_job_dead_letters_after_max_attempts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
                failure_key="failure-2",
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
                first_seen_at=datetime.now(UTC) - timedelta(minutes=10),
                last_seen_at=datetime.now(UTC) - timedelta(minutes=10),
                next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
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
            raise RuntimeError("still failing")

    failure_store = IngestionFailureStore(
        session_local,
        max_attempts=2,
        retry_backoff_minutes="1,2",
    )
    job = IngestionFailureRetryJob(
        session_local,
        failure_store,
        lambda: MockFinnhub(),
        default_resolution="D",
        default_lookback_days=365,
        batch_size=20,
    )

    result = job.run()

    assert result.due_failures == 1
    assert result.attempted == 1
    assert result.retried_success == 0
    assert result.retry_failed == 0
    assert result.dead_lettered == 1

    with session_local() as session:
        failure_row = session.scalar(select(IngestionFailure))

    assert failure_row is not None
    assert failure_row.status == "dead"
    assert failure_row.attempt_count == 2
    assert failure_row.resolved_at is not None
