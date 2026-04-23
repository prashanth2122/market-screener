"""Tests for indicator snapshot write workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, IndicatorSnapshot, Price
from market_screener.jobs.indicator_snapshot import IndicatorSnapshotJob


class FakeTAEngine:
    def sma(self, close_prices: list[float], *, window: int) -> list[float | None]:
        if not close_prices:
            return []
        return [None] * (len(close_prices) - 1) + [sum(close_prices) / len(close_prices)]

    def rsi(self, close_prices: list[float], *, window: int = 14) -> list[float | None]:
        if not close_prices:
            return []
        return [None] + [50.0] * (len(close_prices) - 1)

    def macd(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        if not close_prices:
            return []
        return [None] + [0.2] * (len(close_prices) - 1)

    def macd_signal(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        if not close_prices:
            return []
        return [None] + [0.1] * (len(close_prices) - 1)

    def atr(
        self,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
        *,
        window: int = 14,
    ) -> list[float | None]:
        if not close_prices:
            return []
        output = [None]
        output.extend([high - low for high, low in zip(high_prices[1:], low_prices[1:])])
        return output

    def bollinger_hband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        if not close_prices:
            return []
        return [None] + [close + window_dev for close in close_prices[1:]]

    def bollinger_lband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        if not close_prices:
            return []
        return [None] + [close - window_dev for close in close_prices[1:]]


def test_indicator_snapshot_job_writes_rows_for_active_assets() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    aapl_id: int

    with session_local() as session:
        aapl = Asset(
            symbol="AAPL",
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
        session.add_all([aapl, nvda])
        session.flush()
        aapl_id = aapl.id
        for days_ago, close in (
            (3, Decimal("100")),
            (2, Decimal("101")),
            (1, Decimal("102")),
        ):
            ts = now - timedelta(days=days_ago)
            session.add(
                Price(
                    asset_id=aapl.id,
                    ts=ts,
                    open=close,
                    high=close + Decimal("1"),
                    low=close - Decimal("1"),
                    close=close,
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                )
            )
        session.commit()

    job = IndicatorSnapshotJob(
        session_local,
        symbol_limit=10,
        price_lookback_rows=300,
        snapshot_source="ta_v1",
        ta_engine=FakeTAEngine(),
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 2
    assert result.processed_assets == 2
    assert result.failed_assets == 0
    assert result.snapshots_written == 3
    assert result.snapshots_skipped == 0
    assert result.snapshot_source == "ta_v1"
    assert result.overall_success is True

    with session_local() as session:
        rows = list(
            session.scalars(
                select(IndicatorSnapshot)
                .where(IndicatorSnapshot.asset_id == aapl_id)
                .order_by(IndicatorSnapshot.ts.asc())
            ).all()
        )

    assert len(rows) == 3
    assert rows[0].ma50 is None
    assert float(rows[1].rsi14) == 50.0
    assert float(rows[2].macd) == 0.2
    assert float(rows[2].macd_signal) == 0.1
    assert float(rows[2].atr14) == 2.0
    assert float(rows[2].bb_upper) == 104.0
    assert float(rows[2].bb_lower) == 100.0


def test_indicator_snapshot_job_skips_existing_rows_on_repeat_runs() -> None:
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
        session.add(aapl)
        session.flush()
        for days_ago, close in (
            (3, Decimal("100")),
            (2, Decimal("101")),
            (1, Decimal("102")),
        ):
            ts = now - timedelta(days=days_ago)
            session.add(
                Price(
                    asset_id=aapl.id,
                    ts=ts,
                    open=close,
                    high=close + Decimal("1"),
                    low=close - Decimal("1"),
                    close=close,
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                )
            )
        session.commit()

    job = IndicatorSnapshotJob(
        session_local,
        symbol_limit=10,
        price_lookback_rows=300,
        snapshot_source="ta_v1",
        ta_engine=FakeTAEngine(),
    )

    first = job.run(now_utc=now)
    second = job.run(now_utc=now)

    assert first.snapshots_written == 3
    assert first.snapshots_skipped == 0
    assert second.snapshots_written == 0
    assert second.snapshots_skipped == 3
