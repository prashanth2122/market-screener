"""Tests for score/signal history backfill workflow."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    NewsEvent,
    ScoreHistory,
    SignalHistory,
)
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.score_signal_backfill import (
    ScoreSignalBackfillJob,
    run_score_signal_backfill,
)


class _FakeSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def __enter__(self) -> "_FakeSession":
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
    def _factory() -> _FakeSession:
        return _FakeSession(store)

    return JobAuditTrail(_factory)


def _seed_backfill_data(session_local, *, now: datetime) -> None:
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
                    ts=now - timedelta(days=2),
                    ma50=Decimal("110.0"),
                    ma200=Decimal("100.0"),
                    rsi14=Decimal("58.0"),
                    macd=Decimal("1.2"),
                    macd_signal=Decimal("0.9"),
                    atr14=Decimal("2.0"),
                    bb_upper=Decimal("120.0"),
                    bb_lower=Decimal("95.0"),
                    source="ta_v1",
                ),
                IndicatorSnapshot(
                    asset_id=asset.id,
                    ts=now - timedelta(days=1),
                    ma50=Decimal("112.0"),
                    ma200=Decimal("101.0"),
                    rsi14=Decimal("60.0"),
                    macd=Decimal("1.4"),
                    macd_signal=Decimal("1.0"),
                    atr14=Decimal("2.1"),
                    bb_upper=Decimal("122.0"),
                    bb_lower=Decimal("96.0"),
                    source="ta_v1",
                ),
            ]
        )
        session.add_all(
            [
                FundamentalsSnapshot(
                    asset_id=asset.id,
                    as_of_ts=now - timedelta(days=120),
                    period_type="annual",
                    period_end=date(2024, 12, 31),
                    source="fmp_v1",
                    revenue=Decimal("1000.0"),
                    gross_profit=Decimal("460.0"),
                    ebit=Decimal("130.0"),
                    net_income=Decimal("110.0"),
                    operating_cash_flow=Decimal("125.0"),
                    total_assets=Decimal("900.0"),
                    total_liabilities=Decimal("520.0"),
                    current_assets=Decimal("320.0"),
                    current_liabilities=Decimal("210.0"),
                    long_term_debt=Decimal("180.0"),
                    retained_earnings=Decimal("150.0"),
                    shares_outstanding=Decimal("100.0"),
                    market_cap=Decimal("1500.0"),
                    eps_basic=Decimal("2.10"),
                    eps_diluted=Decimal("2.00"),
                ),
                FundamentalsSnapshot(
                    asset_id=asset.id,
                    as_of_ts=now - timedelta(days=30),
                    period_type="annual",
                    period_end=date(2025, 12, 31),
                    source="fmp_v1",
                    revenue=Decimal("1200.0"),
                    gross_profit=Decimal("560.0"),
                    ebit=Decimal("170.0"),
                    net_income=Decimal("145.0"),
                    operating_cash_flow=Decimal("160.0"),
                    total_assets=Decimal("980.0"),
                    total_liabilities=Decimal("530.0"),
                    current_assets=Decimal("360.0"),
                    current_liabilities=Decimal("205.0"),
                    long_term_debt=Decimal("170.0"),
                    retained_earnings=Decimal("190.0"),
                    shares_outstanding=Decimal("99.0"),
                    market_cap=Decimal("1850.0"),
                    eps_basic=Decimal("2.80"),
                    eps_diluted=Decimal("2.70"),
                ),
            ]
        )
        session.add_all(
            [
                NewsEvent(
                    asset_id=asset.id,
                    published_at=now - timedelta(days=2, hours=2),
                    source="marketaux_v1",
                    title="Company beats estimates with strong growth",
                    sentiment_score=Decimal("0.4500"),
                    event_type=None,
                    risk_flag=False,
                ),
                NewsEvent(
                    asset_id=asset.id,
                    published_at=now - timedelta(days=1, hours=2),
                    source="marketaux_v1",
                    title="Regulatory query remains manageable",
                    sentiment_score=Decimal("0.0500"),
                    event_type="regulatory",
                    risk_flag=True,
                ),
            ]
        )
        session.commit()


def test_score_signal_backfill_job_writes_history_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    _seed_backfill_data(session_local, now=now)

    job = ScoreSignalBackfillJob(
        session_local,
        symbol_limit=10,
        lookback_days=90,
        indicator_source="ta_v1",
        fundamentals_source="fmp_v1",
        news_source_filter="marketaux_v1",
        news_lookback_hours=72,
        sentiment_half_life_hours=24,
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 1
    assert result.processed_assets == 1
    assert result.failed_assets == 0
    assert result.days_considered == 2
    assert result.score_rows_written == 2
    assert result.signal_rows_written == 2
    assert result.skipped_existing_rows == 0

    with session_local() as session:
        score_rows = session.scalars(
            select(ScoreHistory).order_by(ScoreHistory.as_of_ts.asc())
        ).all()
        signal_rows = session.scalars(
            select(SignalHistory).order_by(SignalHistory.as_of_ts.asc())
        ).all()

    assert len(score_rows) == 2
    assert len(signal_rows) == 2
    assert all(row.model_version == "v1.0.1" for row in score_rows)
    assert all(row.signal in {"strong_buy", "buy", "watch", "avoid"} for row in signal_rows)


def test_score_signal_backfill_wrapper_skips_repeated_daily_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    _seed_backfill_data(session_local, now=now)

    settings = Settings(
        score_backfill_symbol_limit=10,
        score_backfill_lookback_days=90,
        score_backfill_indicator_source="ta_v1",
        score_backfill_fundamentals_source="fmp_v1",
        score_backfill_news_source_filter="marketaux_v1",
        score_backfill_news_lookback_hours=72,
        score_backfill_sentiment_half_life_hours=24,
    )
    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)

    first = run_score_signal_backfill(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now,
    )
    second = run_score_signal_backfill(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now + timedelta(hours=1),
    )

    assert first.idempotent_skip is False
    assert first.score_rows_written > 0
    assert second.idempotent_skip is True
    assert second.score_rows_written == 0
    assert second.signal_rows_written == 0
