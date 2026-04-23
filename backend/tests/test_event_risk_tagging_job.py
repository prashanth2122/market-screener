"""Tests for event-risk tagging pipeline workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.event_risk_tagging import EventRiskTaggingJob, run_event_risk_tagging


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


def test_event_risk_tagging_job_updates_event_type_and_risk_flag() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
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
        btc = Asset(
            symbol="BTC",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, btc])
        session.flush()
        session.add_all(
            [
                NewsEvent(
                    asset_id=aapl.id,
                    published_at=now - timedelta(hours=2),
                    source="marketaux_v1",
                    title="SEC probe launched after accounting fraud claim",
                    sentiment_score=Decimal("-0.2000"),
                    event_type=None,
                    risk_flag=None,
                ),
                NewsEvent(
                    asset_id=aapl.id,
                    published_at=now - timedelta(hours=3),
                    source="marketaux_v1",
                    title="Analyst update",
                    description="Unexpected negative sentiment shock in report",
                    sentiment_score=Decimal("-0.6000"),
                    event_type=None,
                    risk_flag=None,
                ),
                NewsEvent(
                    asset_id=btc.id,
                    published_at=now - timedelta(hours=90),
                    source="marketaux_v1",
                    title="Old article outside lookback",
                    sentiment_score=Decimal("-0.9000"),
                    event_type=None,
                    risk_flag=None,
                ),
            ]
        )
        session.commit()

    job = EventRiskTaggingJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        source_filter="marketaux_v1",
        negative_sentiment_threshold=-0.35,
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 2
    assert result.processed_assets == 2
    assert result.failed_assets == 0
    assert result.assets_without_articles == 1
    assert result.articles_scanned == 2
    assert result.articles_updated == 2
    assert result.high_risk_articles == 2

    with session_local() as session:
        rows = session.scalars(
            select(NewsEvent).where(NewsEvent.asset_id == 1).order_by(NewsEvent.published_at.desc())
        ).all()
    assert rows[0].event_type in {"fraud_or_accounting", "regulatory"}
    assert rows[0].risk_flag is True
    assert rows[1].event_type == "sentiment_shock"
    assert rows[1].risk_flag is True
    assert isinstance(rows[1].details, dict)
    assert rows[1].details.get("event_risk_sentiment_triggered") is True


def test_event_risk_tagging_wrapper_skips_repeated_hourly_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
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
        session.add(
            NewsEvent(
                asset_id=aapl.id,
                published_at=now - timedelta(hours=2),
                source="marketaux_v1",
                title="Legal dispute emerges after downgrade",
                sentiment_score=Decimal("-0.4500"),
            )
        )
        session.commit()

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        event_risk_symbol_limit=10,
        event_risk_lookback_hours=72,
        event_risk_source_filter="marketaux_v1",
        event_risk_negative_sentiment_threshold=-0.35,
    )

    first = run_event_risk_tagging(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now,
    )
    second = run_event_risk_tagging(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now + timedelta(minutes=15),
    )

    assert first.idempotent_skip is False
    assert first.processed_assets == 1
    assert second.idempotent_skip is True
    assert second.processed_assets == 0
