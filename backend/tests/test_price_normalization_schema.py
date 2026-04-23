"""Tests for shared price normalization schema."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, Price
from market_screener.jobs.crypto_ohlcv import CryptoCandlePoint
from market_screener.jobs.equity_ohlcv import CandlePoint
from market_screener.jobs.macro_ohlcv import MacroCandlePoint
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    persist_normalized_prices,
)


def test_all_ingestion_jobs_share_single_price_point_schema() -> None:
    assert CandlePoint is NormalizedPricePoint
    assert CryptoCandlePoint is NormalizedPricePoint
    assert MacroCandlePoint is NormalizedPricePoint


def test_persist_normalized_prices_skips_duplicate_timestamps() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        asset = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.commit()
        asset_id = asset.id

    points = [
        NormalizedPricePoint(
            ts=datetime(2026, 4, 23, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=Decimal("1000"),
        )
    ]

    first = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-1",
        points=points,
    )
    second = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-2",
        points=points,
    )

    assert first == (1, 0)
    assert second == (0, 1)

    with session_local() as session:
        stored = session.scalars(select(Price)).all()
    assert len(stored) == 1


def test_persist_normalized_prices_normalizes_offset_timestamps_to_utc() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        asset = Asset(
            symbol="BTCUSD",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.commit()
        asset_id = asset.id

    ist = timezone(timedelta(hours=5, minutes=30))
    utc_point = NormalizedPricePoint(
        ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )
    ist_equivalent_point = NormalizedPricePoint(
        ts=datetime(2026, 4, 23, 5, 30, tzinfo=ist),
        open=Decimal("101"),
        high=Decimal("102"),
        low=Decimal("100"),
        close=Decimal("101.5"),
        volume=Decimal("1500"),
    )

    first = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-1",
        points=[utc_point],
    )
    second = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-2",
        points=[ist_equivalent_point],
    )

    assert first == (1, 0)
    assert second == (0, 1)

    with session_local() as session:
        stored = session.scalars(select(Price)).one()

    assert normalize_to_utc(stored.ts) == datetime(2026, 4, 23, 0, 0, tzinfo=UTC)


def test_persist_normalized_prices_treats_naive_timestamps_as_utc() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        asset = Asset(
            symbol="EURUSD",
            asset_type="forex",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.commit()
        asset_id = asset.id

    naive_point = NormalizedPricePoint(
        ts=datetime(2026, 4, 23, 0, 0),
        open=Decimal("1.1"),
        high=Decimal("1.2"),
        low=Decimal("1.0"),
        close=Decimal("1.15"),
        volume=None,
    )
    utc_equivalent_point = NormalizedPricePoint(
        ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
        open=Decimal("1.11"),
        high=Decimal("1.22"),
        low=Decimal("1.01"),
        close=Decimal("1.16"),
        volume=None,
    )

    first = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-1",
        points=[naive_point],
    )
    second = persist_normalized_prices(
        session_local,
        asset_id=asset_id,
        source="provider_a",
        ingest_id="ingest-2",
        points=[utc_equivalent_point],
    )

    assert first == (1, 0)
    assert second == (0, 1)

    with session_local() as session:
        stored = session.scalars(select(Price)).one()

    assert normalize_to_utc(stored.ts) == datetime(2026, 4, 23, 0, 0, tzinfo=UTC)
