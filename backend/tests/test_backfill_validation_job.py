"""Tests for equity backfill validation workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.backfill_validation import EquityBackfillValidationJob


def test_backfill_validation_passes_when_symbols_have_recent_coverage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    symbols = ["AAPL", "MSFT", "NVDA"]

    with session_local() as session:
        assets: list[Asset] = []
        for symbol in symbols:
            asset = Asset(
                symbol=symbol,
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
            session.add(asset)
            assets.append(asset)
        session.flush()

        for asset in assets:
            for days_ago, close in (
                (1, Decimal("101")),
                (2, Decimal("100")),
                (4, Decimal("99")),
            ):
                ts = now - timedelta(days=days_ago)
                session.add(
                    Price(
                        asset_id=asset.id,
                        ts=ts,
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=Decimal("1000"),
                        source="finnhub",
                        ingest_id="seed",
                    )
                )
        session.commit()

    job = EquityBackfillValidationJob(
        session_local,
        symbol_limit=20,
        lookback_days=7,
        min_rows=3,
        max_last_row_age_days=4,
    )
    result = job.run(now_utc=now)

    assert result.checked_symbols == 3
    assert result.passed_symbols == 3
    assert result.failed_symbols == 0
    assert result.overall_success is True
    assert all(status.is_backfilled for status in result.symbol_statuses)


def test_backfill_validation_reports_missing_insufficient_and_stale() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    with session_local() as session:
        aapl = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        msft = Asset(
            symbol="MSFT",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        nvda = Asset(
            symbol="NVDA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, msft, nvda])
        session.flush()

        session.add(
            Price(
                asset_id=aapl.id,
                ts=now - timedelta(days=1),
                open=Decimal("100"),
                high=Decimal("100"),
                low=Decimal("100"),
                close=Decimal("100"),
                volume=Decimal("1000"),
                source="finnhub",
                ingest_id="seed",
            )
        )
        session.add(
            Price(
                asset_id=msft.id,
                ts=now - timedelta(days=6),
                open=Decimal("200"),
                high=Decimal("200"),
                low=Decimal("200"),
                close=Decimal("200"),
                volume=Decimal("1000"),
                source="finnhub",
                ingest_id="seed",
            )
        )
        session.add(
            Price(
                asset_id=msft.id,
                ts=now - timedelta(days=6, hours=1),
                open=Decimal("199"),
                high=Decimal("199"),
                low=Decimal("199"),
                close=Decimal("199"),
                volume=Decimal("1000"),
                source="finnhub",
                ingest_id="seed",
            )
        )
        session.add(
            Price(
                asset_id=msft.id,
                ts=now - timedelta(days=5, hours=20),
                open=Decimal("198"),
                high=Decimal("198"),
                low=Decimal("198"),
                close=Decimal("198"),
                volume=Decimal("1000"),
                source="finnhub",
                ingest_id="seed",
            )
        )
        session.commit()

    job = EquityBackfillValidationJob(
        session_local,
        symbol_limit=20,
        lookback_days=7,
        min_rows=3,
        max_last_row_age_days=4,
    )
    result = job.run(now_utc=now)

    assert result.checked_symbols == 3
    assert result.passed_symbols == 0
    assert result.failed_symbols == 3
    assert result.overall_success is False

    by_symbol = {status.symbol: status for status in result.symbol_statuses}
    assert by_symbol["AAPL"].failure_reason == "insufficient_rows"
    assert by_symbol["MSFT"].failure_reason == "stale_latest_row"
    assert by_symbol["NVDA"].failure_reason == "missing_rows"
