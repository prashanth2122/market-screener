"""Tests for dead-letter queue routing of non-retryable ingestion payloads."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.core.trading_calendar import TradingCalendar
from market_screener.db.models.core import Asset, DeadLetterPayload, IngestionFailure
from market_screener.jobs.dead_letters import DeadLetterStore
from market_screener.jobs.equity_ohlcv import EquityOhlcvIngestionJob
from market_screener.jobs.ingestion_adapters import (
    AdapterNormalizationError,
    EquityIngestionAdapter,
)
from market_screener.jobs.ingestion_failures import IngestionFailureStore


def test_equity_ohlcv_routes_normalization_errors_to_dead_letter() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    IngestionFailure.__table__.create(engine)
    DeadLetterPayload.__table__.create(engine)
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

    failure_store = IngestionFailureStore(
        session_local,
        max_attempts=3,
        retry_backoff_minutes="5",
    )
    dead_letter_store = DeadLetterStore(session_local)

    class _BadAdapter(EquityIngestionAdapter):
        def fetch_candles(
            self,
            symbol: str,
            *,
            resolution: str,
            from_unix: int,
            to_unix: int,
        ):
            raise AdapterNormalizationError(
                "payload_invalid_shape",
                payload={"provider": "finnhub", "symbol": symbol, "raw": {"c": None}},
            )

    @contextmanager
    def _adapter_factory():
        yield _BadAdapter()

    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: None,
        resolution="D",
        lookback_days=30,
        failure_store=failure_store,
        dead_letter_store=dead_letter_store,
        trading_calendar=TradingCalendar(),
        adapter_factory=_adapter_factory,
    )

    result = job.run(now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))
    assert result.failed_symbols == 1

    with session_local() as session:
        failures = session.scalar(select(func.count()).select_from(IngestionFailure))
        dlq_rows = session.scalars(select(DeadLetterPayload)).all()

    assert failures == 0
    assert len(dlq_rows) == 1
    assert dlq_rows[0].job_name == "equity_ohlcv_ingestion"
    assert dlq_rows[0].asset_symbol == "AAPL"
    assert dlq_rows[0].provider_name == "finnhub"
    assert dlq_rows[0].payload_type == "ohlcv_candles"
    assert dlq_rows[0].reason == "normalization_error"
    assert dlq_rows[0].seen_count == 1

    assert dlq_rows[0].dead_letter_key.startswith("dead_letter:")
