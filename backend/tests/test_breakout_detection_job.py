"""Tests for breakout detection workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, IndicatorSnapshot, Price
from market_screener.jobs.breakout_detection import BreakoutDetectionJob


def test_breakout_detection_job_classifies_upside_downside_and_none() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
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
        tsla = Asset(
            symbol="TSLA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, msft, nvda, tsla])
        session.flush()

        # AAPL upside breakout.
        session.add_all(
            [
                Price(
                    asset_id=aapl.id,
                    ts=now - timedelta(days=2),
                    open=Decimal("99"),
                    high=Decimal("100"),
                    low=Decimal("97"),
                    close=Decimal("99"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=aapl.id,
                    ts=now - timedelta(days=1),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("98"),
                    close=Decimal("100"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=aapl.id,
                    ts=now,
                    open=Decimal("102"),
                    high=Decimal("104"),
                    low=Decimal("101"),
                    close=Decimal("103"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
            ]
        )
        session.add(
            IndicatorSnapshot(
                asset_id=aapl.id,
                ts=now,
                ma50=Decimal("101"),
                ma200=Decimal("99"),
                rsi14=Decimal("60"),
                macd=Decimal("0.7"),
                macd_signal=Decimal("0.3"),
                atr14=Decimal("3.5"),
                bb_upper=Decimal("102"),
                bb_lower=Decimal("96"),
                source="ta_v1",
            )
        )

        # MSFT downside breakout.
        session.add_all(
            [
                Price(
                    asset_id=msft.id,
                    ts=now - timedelta(days=2),
                    open=Decimal("101"),
                    high=Decimal("103"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=msft.id,
                    ts=now - timedelta(days=1),
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("98"),
                    close=Decimal("100"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=msft.id,
                    ts=now,
                    open=Decimal("96"),
                    high=Decimal("97"),
                    low=Decimal("94"),
                    close=Decimal("95"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
            ]
        )
        session.add(
            IndicatorSnapshot(
                asset_id=msft.id,
                ts=now,
                ma50=Decimal("98"),
                ma200=Decimal("101"),
                rsi14=Decimal("40"),
                macd=Decimal("-0.7"),
                macd_signal=Decimal("-0.2"),
                atr14=Decimal("2.5"),
                bb_upper=Decimal("103"),
                bb_lower=Decimal("96"),
                source="ta_v1",
            )
        )

        # NVDA no breakout.
        session.add_all(
            [
                Price(
                    asset_id=nvda.id,
                    ts=now - timedelta(days=2),
                    open=Decimal("200"),
                    high=Decimal("202"),
                    low=Decimal("198"),
                    close=Decimal("200"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=nvda.id,
                    ts=now - timedelta(days=1),
                    open=Decimal("201"),
                    high=Decimal("203"),
                    low=Decimal("199"),
                    close=Decimal("201"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=nvda.id,
                    ts=now,
                    open=Decimal("201"),
                    high=Decimal("202"),
                    low=Decimal("200"),
                    close=Decimal("201"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
            ]
        )

        # TSLA insufficient history.
        session.add(
            Price(
                asset_id=tsla.id,
                ts=now,
                open=Decimal("250"),
                high=Decimal("252"),
                low=Decimal("248"),
                close=Decimal("251"),
                volume=Decimal("1000"),
                source="finnhub",
                ingest_id="seed",
            )
        )

        session.commit()

    job = BreakoutDetectionJob(
        session_local,
        symbol_limit=10,
        lookback_bars=20,
        breakout_buffer_ratio=0.002,
        indicator_source="ta_v1",
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 4
    assert result.classified_assets == 4
    assert result.missing_history_assets == 1
    assert result.breakout_counts == {
        "downside_breakout": 1,
        "none": 1,
        "unknown": 1,
        "upside_breakout": 1,
    }
    assert result.overall_success is False

    by_symbol = {status.symbol: status for status in result.statuses}
    assert by_symbol["AAPL"].signal == "upside_breakout"
    assert by_symbol["MSFT"].signal == "downside_breakout"
    assert by_symbol["NVDA"].signal == "none"
    assert by_symbol["TSLA"].signal == "unknown"
    assert by_symbol["TSLA"].reasons == ["insufficient_price_history"]


def test_breakout_detection_job_uses_indicator_source_filter() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
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
                Price(
                    asset_id=asset.id,
                    ts=now - timedelta(days=2),
                    open=Decimal("99"),
                    high=Decimal("100"),
                    low=Decimal("97"),
                    close=Decimal("99"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=asset.id,
                    ts=now - timedelta(days=1),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("98"),
                    close=Decimal("100"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=asset.id,
                    ts=now,
                    open=Decimal("102"),
                    high=Decimal("103"),
                    low=Decimal("101"),
                    close=Decimal("102"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
            ]
        )
        session.add_all(
            [
                IndicatorSnapshot(
                    asset_id=asset.id,
                    ts=now,
                    ma50=Decimal("101"),
                    ma200=Decimal("99"),
                    rsi14=Decimal("60"),
                    macd=Decimal("0.7"),
                    macd_signal=Decimal("0.3"),
                    atr14=Decimal("1.0"),
                    bb_upper=Decimal("101"),
                    bb_lower=Decimal("96"),
                    source="ta_v1",
                ),
                IndicatorSnapshot(
                    asset_id=asset.id,
                    ts=now,
                    ma50=Decimal("101"),
                    ma200=Decimal("99"),
                    rsi14=Decimal("60"),
                    macd=Decimal("0.7"),
                    macd_signal=Decimal("0.3"),
                    atr14=Decimal("4.0"),
                    bb_upper=Decimal("101"),
                    bb_lower=Decimal("96"),
                    source="ta_alt",
                ),
            ]
        )
        session.commit()

    job = BreakoutDetectionJob(
        session_local,
        symbol_limit=10,
        lookback_bars=20,
        breakout_buffer_ratio=0.002,
        indicator_source="ta_alt",
    )
    result = job.run(now_utc=now)

    assert result.breakout_counts == {"upside_breakout": 1}
    assert result.statuses[0].signal == "upside_breakout"
    assert "atr_expansion" in result.statuses[0].reasons
