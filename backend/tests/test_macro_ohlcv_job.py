"""Tests for forex/commodity OHLCV ingestion job."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.macro_ohlcv import (
    MacroOhlcvIngestionJob,
    MacroOhlcvParseError,
    normalize_alpha_vantage_commodity_daily,
    normalize_alpha_vantage_fx_daily,
)


def test_normalize_alpha_vantage_fx_daily_validates_shape() -> None:
    with pytest.raises(MacroOhlcvParseError):
        normalize_alpha_vantage_fx_daily({"Meta Data": {"a": 1}})


def test_normalize_alpha_vantage_commodity_daily_validates_shape() -> None:
    with pytest.raises(MacroOhlcvParseError):
        normalize_alpha_vantage_commodity_daily({"data": [{"date": "2026-04-22"}]})


def test_macro_ohlcv_job_ingests_and_skips_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="EURUSD",
                asset_type="forex",
                exchange="GLOBAL",
                base_currency="EUR",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            Asset(
                symbol="WTI",
                asset_type="commodity",
                exchange="GLOBAL",
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

    class MockAlphaVantage:
        def __enter__(self) -> "MockAlphaVantage":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_fx_daily(
            self,
            from_symbol: str,
            to_symbol: str,
            *,
            outputsize: str,
        ) -> dict[str, Any]:
            assert from_symbol == "EUR"
            assert to_symbol == "USD"
            assert outputsize == "full"
            return {
                "Time Series FX (Daily)": {
                    "2026-04-22": {
                        "1. open": "1.08",
                        "2. high": "1.09",
                        "3. low": "1.07",
                        "4. close": "1.085",
                    },
                    "2026-04-21": {
                        "1. open": "1.07",
                        "2. high": "1.08",
                        "3. low": "1.06",
                        "4. close": "1.075",
                    },
                }
            }

        def fetch(
            self,
            function: str,
            params: dict[str, str | int | float] | None = None,
        ) -> dict[str, Any]:
            assert function == "WTI"
            assert params == {"interval": "daily"}
            return {
                "data": [
                    {"date": "2026-04-22", "value": "82.5"},
                    {"date": "2026-04-21", "value": "81.8"},
                ]
            }

    job = MacroOhlcvIngestionJob(
        session_local,
        lambda: MockAlphaVantage(),
        lookback_days=365,
        forex_outputsize="full",
        commodity_interval="daily",
    )
    now_utc = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)

    first = job.run(now_utc=now_utc)
    assert first.processed_symbols == 2
    assert first.ingested_rows == 4
    assert first.skipped_rows == 0
    assert first.failed_symbols == 0
    assert first.no_data_symbols == 0
    assert first.unsupported_symbols == 0
    assert first.market_closed_symbols == 0

    second = job.run(now_utc=now_utc)
    assert second.processed_symbols == 2
    assert second.ingested_rows == 0
    assert second.skipped_rows == 4
    assert second.failed_symbols == 0
    assert second.no_data_symbols == 0
    assert second.unsupported_symbols == 0
    assert second.market_closed_symbols == 0

    with session_local() as session:
        prices = session.scalars(select(Price).order_by(Price.ts, Price.asset_id)).all()

    assert len(prices) == 4
    assert all(price.source == "alpha_vantage" for price in prices)
    stored_ts = prices[0].ts.replace(tzinfo=UTC) if prices[0].ts.tzinfo is None else prices[0].ts
    assert stored_ts == datetime(2026, 4, 21, tzinfo=UTC)


def test_macro_ohlcv_job_tracks_unsupported_no_data_and_failures() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="EURUSD",
                asset_type="forex",
                exchange="GLOBAL",
                base_currency="EUR",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            Asset(
                symbol="USDINR",
                asset_type="forex",
                exchange="GLOBAL",
                base_currency=None,
                quote_currency="INR",
                active=True,
            )
        )
        session.add(
            Asset(
                symbol="WTI",
                asset_type="commodity",
                exchange="GLOBAL",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    class MockAlphaVantage:
        def __enter__(self) -> "MockAlphaVantage":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_fx_daily(
            self,
            from_symbol: str,
            to_symbol: str,
            *,
            outputsize: str,
        ) -> dict[str, Any]:
            assert from_symbol == "EUR"
            return {"Time Series FX (Daily)": {}}

        def fetch(
            self,
            function: str,
            params: dict[str, str | int | float] | None = None,
        ) -> dict[str, Any]:
            assert function == "WTI"
            raise RuntimeError("provider failure")

    job = MacroOhlcvIngestionJob(
        session_local,
        lambda: MockAlphaVantage(),
        lookback_days=365,
        forex_outputsize="full",
        commodity_interval="daily",
    )
    result = job.run(now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 3
    assert result.ingested_rows == 0
    assert result.skipped_rows == 0
    assert result.failed_symbols == 1
    assert result.no_data_symbols == 1
    assert result.unsupported_symbols == 1
    assert result.market_closed_symbols == 0


def test_macro_ohlcv_job_skips_on_market_closure() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="EURUSD",
                asset_type="forex",
                exchange="GLOBAL",
                base_currency="EUR",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            Asset(
                symbol="WTI",
                asset_type="commodity",
                exchange="GLOBAL",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    class MockAlphaVantage:
        def __enter__(self) -> "MockAlphaVantage":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_fx_daily(
            self,
            from_symbol: str,
            to_symbol: str,
            *,
            outputsize: str,
        ) -> dict[str, Any]:
            raise AssertionError("provider should not be called on closed market day")

        def fetch(
            self,
            function: str,
            params: dict[str, str | int | float] | None = None,
        ) -> dict[str, Any]:
            raise AssertionError("provider should not be called on closed market day")

    job = MacroOhlcvIngestionJob(
        session_local,
        lambda: MockAlphaVantage(),
        lookback_days=365,
        forex_outputsize="full",
        commodity_interval="daily",
    )
    result = job.run(now_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 2
    assert result.ingested_rows == 0
    assert result.skipped_rows == 0
    assert result.failed_symbols == 0
    assert result.no_data_symbols == 0
    assert result.unsupported_symbols == 0
    assert result.market_closed_symbols == 2
