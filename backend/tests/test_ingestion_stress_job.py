"""Tests for ingestion stress test workflow."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, Price
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.ingestion_stress import (
    IngestionStressTestJob,
    run_ingestion_stress_test,
)


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


class MockCoinGecko:
    def __enter__(self) -> "MockCoinGecko":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def get_coin_ohlc(self, coin_id: str, *, vs_currency: str, days: int) -> list[list[float]]:
        assert coin_id == "bitcoin"
        assert vs_currency == "usd"
        assert days == 365
        return [[1704067200000, 200.0, 202.0, 199.0, 201.0]]


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
                }
            }
        }

    def fetch(
        self,
        function: str,
        params: dict[str, str | int | float] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("fetch should not be called for forex-only test")


class FakeAuditSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def __enter__(self) -> "FakeAuditSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def add(self, job_row) -> None:
        self._store[job_row.run_id] = job_row

    def merge(self, job_row):
        self._store[job_row.run_id] = job_row
        return job_row

    def commit(self) -> None:
        return None


def _build_audit_trail(store: dict[str, Any]) -> JobAuditTrail:
    def _factory() -> FakeAuditSession:
        return FakeAuditSession(store)

    return JobAuditTrail(_factory)


def _seed_assets(session_local) -> None:
    with session_local() as session:
        session.add_all(
            [
                Asset(
                    symbol="AAPL",
                    asset_type="equity",
                    exchange="US",
                    quote_currency="USD",
                    active=True,
                ),
                Asset(
                    symbol="BTC",
                    asset_type="crypto",
                    exchange="GLOBAL",
                    quote_currency="USD",
                    active=True,
                ),
                Asset(
                    symbol="EURUSD",
                    asset_type="forex",
                    exchange="GLOBAL",
                    base_currency="EUR",
                    quote_currency="USD",
                    active=True,
                ),
            ]
        )
        session.commit()


def _create_symbol_universe(tmp_path: Path) -> Path:
    path = tmp_path / "symbols.json"
    path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
                        "coingecko_id": "bitcoin",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_ingestion_stress_job_runs_all_segments_for_active_symbols(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    _seed_assets(session_local)
    universe_path = _create_symbol_universe(tmp_path)

    settings = Settings(
        symbol_universe_file=str(universe_path),
        equity_ohlcv_resolution="D",
        equity_ohlcv_lookback_days=365,
        crypto_ohlcv_vs_currency="usd",
        crypto_ohlcv_days=365,
        macro_ohlcv_lookback_days=365,
        macro_ohlcv_forex_outputsize="full",
        macro_ohlcv_commodity_interval="daily",
    )
    job = IngestionStressTestJob(
        session_local,
        settings,
        symbol_limit=100,
        finnhub_client_factory=lambda: MockFinnhub(),
        coingecko_client_factory=lambda: MockCoinGecko(),
        alpha_vantage_client_factory=lambda: MockAlphaVantage(),
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.symbols_under_test == 3
    assert result.processed_symbols == 3
    assert result.ingested_rows == 3
    assert result.failed_symbols == 0
    assert result.overall_success is True
    assert {segment.segment for segment in result.segments} == {"equity", "crypto", "macro"}

    with session_local() as session:
        stored = session.scalars(select(Price)).all()
    assert len(stored) == 3


def test_ingestion_stress_wrapper_emits_audit_details(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    _seed_assets(session_local)
    universe_path = _create_symbol_universe(tmp_path)

    settings = Settings(
        symbol_universe_file=str(universe_path),
        ingestion_stress_symbol_limit=100,
        equity_ohlcv_resolution="D",
        equity_ohlcv_lookback_days=365,
        crypto_ohlcv_vs_currency="usd",
        crypto_ohlcv_days=365,
        macro_ohlcv_lookback_days=365,
        macro_ohlcv_forex_outputsize="full",
        macro_ohlcv_commodity_interval="daily",
    )
    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)

    result = run_ingestion_stress_test(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        finnhub_client_factory=lambda: MockFinnhub(),
        coingecko_client_factory=lambda: MockCoinGecko(),
        alpha_vantage_client_factory=lambda: MockAlphaVantage(),
    )

    assert result.processed_symbols == 3
    rows = list(store.values())
    assert len(rows) == 1
    row = rows[0]
    assert row.job_name == "ingestion_stress_test"
    assert row.status == "completed"
    assert row.details["symbols_under_test"] == 3
    assert row.details["processed_symbols"] == 3
    assert row.details["overall_success"] is True
