"""Tests for crypto OHLCV ingestion job."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.crypto_ohlcv import (
    CryptoOhlcvIngestionJob,
    CryptoOhlcvParseError,
    normalize_coingecko_ohlc,
)


def test_normalize_coingecko_ohlc_validates_shape() -> None:
    with pytest.raises(CryptoOhlcvParseError):
        normalize_coingecko_ohlc([["bad-ts", 100, 110, 90, 105]])


def test_crypto_ohlcv_job_ingests_and_skips_duplicates(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "coingecko_id": "bitcoin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="BTC",
                asset_type="crypto",
                exchange="GLOBAL",
                quote_currency="USD",
                active=True,
            )
        )
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

    class MockCoinGecko:
        def __enter__(self) -> "MockCoinGecko":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_coin_ohlc(self, coin_id: str, *, vs_currency: str, days: int) -> list[list[float]]:
            assert coin_id == "bitcoin"
            assert vs_currency == "usd"
            assert days == 365
            return [
                [1704067200000, 100.0, 102.0, 99.0, 101.0],
                [1704153600000, 101.0, 103.0, 100.0, 102.0],
            ]

    job = CryptoOhlcvIngestionJob(
        session_local,
        lambda: MockCoinGecko(),
        symbol_map_path=universe_path,
        vs_currency="usd",
        days=365,
    )

    first = job.run()
    assert first.processed_symbols == 1
    assert first.ingested_rows == 2
    assert first.skipped_rows == 0
    assert first.failed_symbols == 0
    assert first.no_data_symbols == 0
    assert first.missing_mapping_symbols == 0

    second = job.run()
    assert second.processed_symbols == 1
    assert second.ingested_rows == 0
    assert second.skipped_rows == 2
    assert second.failed_symbols == 0
    assert second.no_data_symbols == 0
    assert second.missing_mapping_symbols == 0

    with session_local() as session:
        prices = session.scalars(select(Price).order_by(Price.ts)).all()

    assert len(prices) == 2
    assert prices[0].source == "coingecko"
    stored_ts = prices[0].ts.replace(tzinfo=UTC) if prices[0].ts.tzinfo is None else prices[0].ts
    assert stored_ts == datetime.fromtimestamp(1704067200, tz=UTC)


def test_crypto_ohlcv_job_tracks_missing_mapping_and_failures(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "coingecko_id": "bitcoin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="BTC",
                asset_type="crypto",
                exchange="GLOBAL",
                quote_currency="USD",
                active=True,
            )
        )
        session.add(
            Asset(
                symbol="ETH",
                asset_type="crypto",
                exchange="GLOBAL",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    class MockCoinGecko:
        def __enter__(self) -> "MockCoinGecko":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_coin_ohlc(self, coin_id: str, *, vs_currency: str, days: int) -> list[list[Any]]:
            assert coin_id == "bitcoin"
            raise RuntimeError("provider failure")

    job = CryptoOhlcvIngestionJob(
        session_local,
        lambda: MockCoinGecko(),
        symbol_map_path=universe_path,
        vs_currency="usd",
        days=365,
    )
    result = job.run()

    assert result.processed_symbols == 2
    assert result.ingested_rows == 0
    assert result.skipped_rows == 0
    assert result.failed_symbols == 1
    assert result.no_data_symbols == 0
    assert result.missing_mapping_symbols == 1
