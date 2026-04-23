"""Tests for relative volume workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, Price
from market_screener.jobs.relative_volume import RelativeVolumeJob


def test_relative_volume_job_classifies_spike_dry_up_normal_unknown() -> None:
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
        tsla = Asset(
            symbol="TSLA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, msft, nvda, tsla])
        session.flush()

        def add_vol(asset_id: int, day_offset: int, volume: Decimal | None) -> None:
            ts = now - timedelta(days=day_offset)
            session.add(
                Price(
                    asset_id=asset_id,
                    ts=ts,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=volume,
                    source="finnhub",
                    ingest_id="seed",
                )
            )

        # AAPL spike.
        add_vol(aapl.id, 2, Decimal("1000"))
        add_vol(aapl.id, 1, Decimal("1000"))
        add_vol(aapl.id, 0, Decimal("2000"))
        # MSFT dry-up.
        add_vol(msft.id, 2, Decimal("1000"))
        add_vol(msft.id, 1, Decimal("1000"))
        add_vol(msft.id, 0, Decimal("500"))
        # NVDA normal.
        add_vol(nvda.id, 2, Decimal("1000"))
        add_vol(nvda.id, 1, Decimal("1000"))
        add_vol(nvda.id, 0, Decimal("1000"))
        # TSLA insufficient.
        add_vol(tsla.id, 0, Decimal("1000"))

        session.commit()

    job = RelativeVolumeJob(
        session_local,
        symbol_limit=10,
        lookback_bars=20,
        spike_threshold=1.5,
        dry_up_threshold=0.7,
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 4
    assert result.classified_assets == 4
    assert result.missing_history_assets == 1
    assert result.state_counts == {
        "dry_up": 1,
        "normal": 1,
        "spike": 1,
        "unknown": 1,
    }
    assert result.overall_success is False

    by_symbol = {status.symbol: status for status in result.statuses}
    assert by_symbol["AAPL"].state == "spike"
    assert by_symbol["MSFT"].state == "dry_up"
    assert by_symbol["NVDA"].state == "normal"
    assert by_symbol["TSLA"].state == "unknown"
    assert by_symbol["TSLA"].reasons == ["insufficient_volume_history"]


def test_relative_volume_job_counts_missing_current_volume_as_unknown() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

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
        session.add_all(
            [
                Price(
                    asset_id=asset.id,
                    ts=now - timedelta(days=1),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=asset.id,
                    ts=now,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=None,
                    source="finnhub",
                    ingest_id="seed",
                ),
            ]
        )
        session.commit()

    job = RelativeVolumeJob(
        session_local,
        symbol_limit=10,
        lookback_bars=20,
        spike_threshold=1.5,
        dry_up_threshold=0.7,
    )
    result = job.run(now_utc=now)

    assert result.state_counts == {"unknown": 1}
    assert result.missing_history_assets == 1
    assert result.statuses[0].reasons == ["missing_current_volume"]
