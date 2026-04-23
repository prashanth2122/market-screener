"""Tests for ingestion adapter interface wiring."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.crypto_ohlcv import CryptoOhlcvIngestionJob
from market_screener.jobs.equity_ohlcv import EquityOhlcvIngestionJob
from market_screener.jobs.macro_ohlcv import MacroOhlcvIngestionJob
from market_screener.jobs.price_normalization import NormalizedPricePoint


def _point(ts: datetime) -> NormalizedPricePoint:
    return NormalizedPricePoint(
        ts=ts,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )


def test_equity_job_accepts_custom_adapter_factory() -> None:
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

    @contextmanager
    def _adapter_factory():
        class StubAdapter:
            def fetch_candles(
                self,
                symbol: str,
                *,
                resolution: str,
                from_unix: int,
                to_unix: int,
            ) -> list[NormalizedPricePoint]:
                assert symbol == "AAPL"
                assert resolution == "D"
                assert from_unix < to_unix
                return [_point(datetime(2026, 4, 22, tzinfo=UTC))]

        yield StubAdapter()

    job = EquityOhlcvIngestionJob(
        session_local,
        lambda: (_ for _ in ()).throw(AssertionError("provider client should not be used")),
        resolution="D",
        lookback_days=365,
        adapter_factory=_adapter_factory,
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 1
    assert result.ingested_rows == 1
    assert result.failed_symbols == 0


def test_crypto_job_accepts_custom_adapter_builder(tmp_path: Path) -> None:
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
        session.commit()

    def _adapter_builder(symbol_map: dict[str, str]):
        assert symbol_map["BTC"] == "bitcoin"

        @contextmanager
        def _adapter_factory():
            class StubAdapter:
                def fetch_candles(
                    self,
                    symbol: str,
                    *,
                    vs_currency: str,
                    days: int,
                ) -> list[NormalizedPricePoint]:
                    assert symbol == "BTC"
                    assert vs_currency == "usd"
                    assert days == 365
                    return [_point(datetime(2026, 4, 22, tzinfo=UTC))]

            yield StubAdapter()

        return _adapter_factory()

    job = CryptoOhlcvIngestionJob(
        session_local,
        lambda: (_ for _ in ()).throw(AssertionError("provider client should not be used")),
        symbol_map_path=universe_path,
        vs_currency="usd",
        days=365,
        adapter_factory_builder=_adapter_builder,
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 1
    assert result.ingested_rows == 1
    assert result.failed_symbols == 0
    assert result.missing_mapping_symbols == 0


def test_macro_job_accepts_custom_adapter_factory() -> None:
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

    @contextmanager
    def _adapter_factory():
        class StubAdapter:
            def fetch_candles(
                self,
                asset: Asset,
                *,
                forex_outputsize: str,
                commodity_interval: str,
                window_start_date: date,
            ) -> list[NormalizedPricePoint] | None:
                assert asset.symbol == "EURUSD"
                assert forex_outputsize == "full"
                assert commodity_interval == "daily"
                assert window_start_date <= date(2026, 4, 22)
                return [_point(datetime(2026, 4, 22, tzinfo=UTC))]

        yield StubAdapter()

    job = MacroOhlcvIngestionJob(
        session_local,
        lambda: (_ for _ in ()).throw(AssertionError("provider client should not be used")),
        lookback_days=365,
        forex_outputsize="full",
        commodity_interval="daily",
        adapter_factory=_adapter_factory,
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.processed_symbols == 1
    assert result.ingested_rows == 1
    assert result.failed_symbols == 0
