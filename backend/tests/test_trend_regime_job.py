"""Tests for trend regime classification job workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, IndicatorSnapshot
from market_screener.jobs.trend_regime import TrendRegimeClassificationJob


def test_trend_regime_job_classifies_latest_indicator_snapshot_per_asset() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
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
        session.add_all(
            [
                IndicatorSnapshot(
                    asset_id=aapl.id,
                    ts=now,
                    ma50=Decimal("105"),
                    ma200=Decimal("100"),
                    rsi14=Decimal("60"),
                    macd=Decimal("0.7"),
                    macd_signal=Decimal("0.3"),
                    atr14=Decimal("2"),
                    bb_upper=Decimal("110"),
                    bb_lower=Decimal("102"),
                    source="ta_v1",
                ),
                IndicatorSnapshot(
                    asset_id=msft.id,
                    ts=now,
                    ma50=Decimal("95"),
                    ma200=Decimal("100"),
                    rsi14=Decimal("40"),
                    macd=Decimal("-0.6"),
                    macd_signal=Decimal("-0.2"),
                    atr14=Decimal("2"),
                    bb_upper=Decimal("101"),
                    bb_lower=Decimal("90"),
                    source="ta_v1",
                ),
            ]
        )
        session.commit()

    job = TrendRegimeClassificationJob(
        session_local,
        symbol_limit=10,
        indicator_source="ta_v1",
        macd_flat_tolerance=0.1,
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 3
    assert result.classified_assets == 3
    assert result.missing_indicator_assets == 1
    assert result.regime_counts == {"bearish": 1, "bullish": 1, "unknown": 1}
    assert result.overall_success is False

    by_symbol = {status.symbol: status for status in result.statuses}
    assert by_symbol["AAPL"].regime == "bullish"
    assert by_symbol["MSFT"].regime == "bearish"
    assert by_symbol["NVDA"].regime == "unknown"
    assert by_symbol["NVDA"].reasons == ["missing_indicator_snapshot"]


def test_trend_regime_job_respects_indicator_source_filter() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
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
                IndicatorSnapshot(
                    asset_id=asset.id,
                    ts=now,
                    ma50=Decimal("95"),
                    ma200=Decimal("100"),
                    rsi14=Decimal("40"),
                    macd=Decimal("-0.6"),
                    macd_signal=Decimal("-0.2"),
                    atr14=Decimal("2"),
                    bb_upper=Decimal("101"),
                    bb_lower=Decimal("90"),
                    source="ta_v1",
                ),
                IndicatorSnapshot(
                    asset_id=asset.id,
                    ts=now,
                    ma50=Decimal("106"),
                    ma200=Decimal("100"),
                    rsi14=Decimal("61"),
                    macd=Decimal("0.8"),
                    macd_signal=Decimal("0.3"),
                    atr14=Decimal("2"),
                    bb_upper=Decimal("111"),
                    bb_lower=Decimal("104"),
                    source="ta_alt",
                ),
            ]
        )
        session.commit()

    job = TrendRegimeClassificationJob(
        session_local,
        symbol_limit=10,
        indicator_source="ta_alt",
        macd_flat_tolerance=0.1,
    )
    result = job.run(now_utc=now)

    assert result.regime_counts == {"bullish": 1}
    assert result.statuses[0].regime == "bullish"
