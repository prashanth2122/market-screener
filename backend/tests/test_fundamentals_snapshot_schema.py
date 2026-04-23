"""Tests for fundamentals snapshot schema design constraints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, FundamentalsSnapshot


def test_fundamentals_snapshot_persists_expected_fields() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
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
        session.flush()
        session.add(
            FundamentalsSnapshot(
                asset_id=asset.id,
                as_of_ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
                period_type="annual",
                period_end=date(2025, 12, 31),
                filing_date=date(2026, 2, 5),
                statement_currency="USD",
                revenue=Decimal("120000000000.0000"),
                gross_profit=Decimal("55000000000.0000"),
                ebit=Decimal("42000000000.0000"),
                net_income=Decimal("39000000000.0000"),
                operating_cash_flow=Decimal("45000000000.0000"),
                total_assets=Decimal("350000000000.0000"),
                total_liabilities=Decimal("230000000000.0000"),
                current_assets=Decimal("140000000000.0000"),
                current_liabilities=Decimal("110000000000.0000"),
                long_term_debt=Decimal("95000000000.0000"),
                retained_earnings=Decimal("22000000000.0000"),
                shares_outstanding=Decimal("15500000000.0000"),
                market_cap=Decimal("2900000000000.0000"),
                eps_basic=Decimal("6.51000000"),
                eps_diluted=Decimal("6.49000000"),
                source="finnhub",
                details={"provider_metric_key": "value"},
            )
        )
        session.commit()

    with session_local() as session:
        row = session.scalar(select(FundamentalsSnapshot))

    assert row is not None
    assert row.period_type == "annual"
    assert row.period_end == date(2025, 12, 31)
    assert row.statement_currency == "USD"
    assert float(row.eps_diluted or 0) == 6.49
    assert row.details == {"provider_metric_key": "value"}


def test_fundamentals_snapshot_unique_constraint_blocks_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    asset_id: int
    with session_local() as session:
        asset = Asset(
            symbol="MSFT",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        asset_id = asset.id
        session.add(
            FundamentalsSnapshot(
                asset_id=asset.id,
                as_of_ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
                period_type="annual",
                period_end=date(2025, 12, 31),
                source="finnhub",
            )
        )
        session.commit()

    with session_local() as session:
        session.add(
            FundamentalsSnapshot(
                asset_id=asset_id,
                as_of_ts=datetime(2026, 4, 24, 0, 0, tzinfo=UTC),
                period_type="annual",
                period_end=date(2025, 12, 31),
                source="finnhub",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_fundamentals_snapshot_allows_same_period_from_different_sources() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        asset = Asset(
            symbol="NVDA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        session.add_all(
            [
                FundamentalsSnapshot(
                    asset_id=asset.id,
                    as_of_ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
                    period_type="annual",
                    period_end=date(2025, 12, 31),
                    source="finnhub",
                ),
                FundamentalsSnapshot(
                    asset_id=asset.id,
                    as_of_ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
                    period_type="annual",
                    period_end=date(2025, 12, 31),
                    source="alpha_vantage",
                ),
            ]
        )
        session.commit()

    with session_local() as session:
        rows = session.scalars(select(FundamentalsSnapshot)).all()
    assert len(rows) == 2
