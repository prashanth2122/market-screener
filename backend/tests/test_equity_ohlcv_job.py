"""Tests for equity OHLCV ingestion job."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.equity_ohlcv import (
    EquityOhlcvIngestionJob,
    EquityOhlcvParseError,
    normalize_finnhub_candles,
)


def test_normalize_finnhub_candles_validates_shape() -> None:
    with pytest.raises(EquityOhlcvParseError):
        normalize_finnhub_candles(
            {"s": "ok", "t": [1], "o": [1.0], "h": [1.0], "l": [1.0], "c": []}
        )


def test_equity_ohlcv_job_ingests_and_skips_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
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
            Asset(
                symbol="BTC",
                asset_type="crypto",
                exchange="GLOBAL",
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
            assert resolution == "D"
            assert from_unix < to_unix
            return {
                "s": "ok",
                "t": [1704067200, 1704153600],
                "o": [100.0, 101.0],
                "h": [102.0, 103.0],
                "l": [99.0, 100.0],
                "c": [101.0, 102.0],
                "v": [1000.0, 1100.0],
            }

    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: MockFinnhub(),
        resolution="D",
        lookback_days=365,
    )
    now_utc = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)

    first = job.run(now_utc=now_utc)
    assert first.processed_symbols == 1
    assert first.ingested_rows == 2
    assert first.skipped_rows == 0
    assert first.failed_symbols == 0
    assert first.no_data_symbols == 0
    assert first.market_closed_symbols == 0

    second = job.run(now_utc=now_utc)
    assert second.processed_symbols == 1
    assert second.ingested_rows == 0
    assert second.skipped_rows == 2
    assert second.failed_symbols == 0
    assert second.no_data_symbols == 0
    assert second.market_closed_symbols == 0

    with session_local() as session:
        prices = session.scalars(select(Price).order_by(Price.ts)).all()

    assert len(prices) == 2
    assert prices[0].source == "finnhub"
    stored_ts = prices[0].ts.replace(tzinfo=UTC) if prices[0].ts.tzinfo is None else prices[0].ts
    assert stored_ts == datetime.fromtimestamp(1704067200, tz=UTC)


def test_equity_ohlcv_job_tracks_no_data_and_failures() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
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
            Asset(
                symbol="MSFT",
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
            if symbol == "AAPL":
                return {
                    "s": "no_data",
                    "t": [],
                    "o": [],
                    "h": [],
                    "l": [],
                    "c": [],
                    "v": [],
                }
            raise RuntimeError("provider failure")

    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: MockFinnhub(),
        resolution="D",
        lookback_days=365,
    )
    result = job.run(now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 2
    assert result.ingested_rows == 0
    assert result.skipped_rows == 0
    assert result.failed_symbols == 1
    assert result.no_data_symbols == 1
    assert result.market_closed_symbols == 0


def test_equity_ohlcv_job_skips_on_market_closure() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
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
            raise AssertionError("provider should not be called on closed market day")

    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: MockFinnhub(),
        resolution="D",
        lookback_days=365,
    )
    result = job.run(now_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 1
    assert result.ingested_rows == 0
    assert result.skipped_rows == 0
    assert result.failed_symbols == 0
    assert result.no_data_symbols == 0
    assert result.market_closed_symbols == 1
