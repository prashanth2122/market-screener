"""Integration tests for ingestion audit metadata wiring."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, Price
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.crypto_ohlcv import run_crypto_ohlcv_ingestion
from market_screener.jobs.equity_ohlcv import run_equity_ohlcv_ingestion
from market_screener.jobs.macro_ohlcv import run_macro_ohlcv_ingestion
from market_screener.jobs.symbol_metadata import run_symbol_metadata_ingestion


class FakeSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def __enter__(self) -> "FakeSession":
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
    def _factory() -> FakeSession:
        return FakeSession(store)

    return JobAuditTrail(_factory)


def test_symbol_metadata_wrapper_emits_audit_details(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "equity",
                        "exchange": "US",
                        "quote_currency": "USD",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)

    result = run_symbol_metadata_ingestion(
        session_factory=session_local,
        universe_path=universe_path,
        audit_trail=audit_trail,
    )

    assert result.created == 1
    rows = list(store.values())
    assert len(rows) == 1
    row = rows[0]
    assert row.job_name == "symbol_metadata_ingestion"
    assert row.status == "completed"
    assert row.details["created"] == 1
    assert row.details["universe_path"] == str(universe_path)
    assert isinstance(row.idempotency_key, str)


def test_equity_ohlcv_wrapper_emits_audit_details(monkeypatch) -> None:
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
        "market_screener.jobs.equity_ohlcv.FinnhubClient.from_settings",
        lambda _settings: MockFinnhub(),
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)

    settings = Settings(
        finnhub_api_key="demo",
        equity_ohlcv_resolution="D",
        equity_ohlcv_lookback_days=365,
    )
    result = run_equity_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )

    assert result.ingested_rows == 1
    rows = list(store.values())
    assert len(rows) == 1
    row = rows[0]
    assert row.job_name == "equity_ohlcv_ingestion"
    assert row.status == "completed"
    assert row.details["provider"] == "finnhub"
    assert row.details["ingested_rows"] == 1
    assert isinstance(row.idempotency_key, str)


def test_symbol_metadata_wrapper_skips_repeated_pull(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "equity",
                        "exchange": "US",
                        "quote_currency": "USD",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)

    first = run_symbol_metadata_ingestion(
        session_factory=session_local,
        universe_path=universe_path,
        audit_trail=audit_trail,
    )
    second = run_symbol_metadata_ingestion(
        session_factory=session_local,
        universe_path=universe_path,
        audit_trail=audit_trail,
    )

    assert first.created == 1
    assert first.idempotent_skip is False
    assert second.idempotent_skip is True
    assert second.processed == 0

    with session_local() as session:
        count = session.scalar(select(func.count()).select_from(Asset))
    assert count == 1


def test_equity_ohlcv_wrapper_skips_repeated_pull(monkeypatch) -> None:
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
        def __init__(self) -> None:
            self.calls = 0

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
            self.calls += 1
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

    mock = MockFinnhub()
    monkeypatch.setattr(
        "market_screener.jobs.equity_ohlcv.FinnhubClient.from_settings",
        lambda _settings: mock,
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        finnhub_api_key="demo",
        equity_ohlcv_resolution="D",
        equity_ohlcv_lookback_days=365,
    )

    first = run_equity_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )
    second = run_equity_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )

    assert first.ingested_rows == 1
    assert first.idempotent_skip is False
    assert second.idempotent_skip is True
    assert second.ingested_rows == 0
    assert mock.calls == 1


def test_crypto_ohlcv_wrapper_emits_audit_details(monkeypatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "coingecko_id": "bitcoin",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
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
            return [[1704067200000, 100.0, 101.0, 99.0, 100.5]]

    monkeypatch.setattr(
        "market_screener.jobs.crypto_ohlcv.CoinGeckoClient.from_settings",
        lambda _settings: MockCoinGecko(),
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        symbol_universe_file=str(universe_path),
        crypto_ohlcv_vs_currency="usd",
        crypto_ohlcv_days=365,
    )

    result = run_crypto_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
    )

    assert result.ingested_rows == 1
    rows = list(store.values())
    assert len(rows) == 1
    row = rows[0]
    assert row.job_name == "crypto_ohlcv_ingestion"
    assert row.status == "completed"
    assert row.details["provider"] == "coingecko"
    assert row.details["ingested_rows"] == 1
    assert isinstance(row.idempotency_key, str)


def test_crypto_ohlcv_wrapper_skips_repeated_pull(monkeypatch, tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "coingecko_id": "bitcoin",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
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
        session.commit()

    class MockCoinGecko:
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self) -> "MockCoinGecko":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_coin_ohlc(self, coin_id: str, *, vs_currency: str, days: int) -> list[list[float]]:
            self.calls += 1
            assert coin_id == "bitcoin"
            assert vs_currency == "usd"
            assert days == 365
            return [[1704067200000, 100.0, 101.0, 99.0, 100.5]]

    mock = MockCoinGecko()
    monkeypatch.setattr(
        "market_screener.jobs.crypto_ohlcv.CoinGeckoClient.from_settings",
        lambda _settings: mock,
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        symbol_universe_file=str(universe_path),
        crypto_ohlcv_vs_currency="usd",
        crypto_ohlcv_days=365,
    )

    first = run_crypto_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
    )
    second = run_crypto_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
    )

    assert first.ingested_rows == 1
    assert first.idempotent_skip is False
    assert second.idempotent_skip is True
    assert second.ingested_rows == 0
    assert mock.calls == 1


def test_macro_ohlcv_wrapper_emits_audit_details(monkeypatch) -> None:
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
                    }
                }
            }

        def fetch(
            self,
            function: str,
            params: dict[str, str | int | float] | None = None,
        ) -> dict[str, Any]:
            raise AssertionError("fetch should not be called for forex-only test")

    monkeypatch.setattr(
        "market_screener.jobs.macro_ohlcv.AlphaVantageClient.from_settings",
        lambda _settings: MockAlphaVantage(),
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        alpha_vantage_api_key="demo",
        macro_ohlcv_lookback_days=365,
        macro_ohlcv_forex_outputsize="full",
        macro_ohlcv_commodity_interval="daily",
    )

    result = run_macro_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )

    assert result.ingested_rows == 1
    rows = list(store.values())
    assert len(rows) == 1
    row = rows[0]
    assert row.job_name == "macro_ohlcv_ingestion"
    assert row.status == "completed"
    assert row.details["provider"] == "alpha_vantage"
    assert row.details["ingested_rows"] == 1
    assert isinstance(row.idempotency_key, str)


def test_macro_ohlcv_wrapper_skips_repeated_pull(monkeypatch) -> None:
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
        session.commit()

    class MockAlphaVantage:
        def __init__(self) -> None:
            self.calls = 0

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
            self.calls += 1
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

    mock = MockAlphaVantage()
    monkeypatch.setattr(
        "market_screener.jobs.macro_ohlcv.AlphaVantageClient.from_settings",
        lambda _settings: mock,
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        alpha_vantage_api_key="demo",
        macro_ohlcv_lookback_days=365,
        macro_ohlcv_forex_outputsize="full",
        macro_ohlcv_commodity_interval="daily",
    )

    first = run_macro_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )
    second = run_macro_ohlcv_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )

    assert first.ingested_rows == 1
    assert first.idempotent_skip is False
    assert second.idempotent_skip is True
    assert second.ingested_rows == 0
    assert mock.calls == 1
