"""Tests for sentiment scoring pipeline workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.sentiment_scoring import run_sentiment_scoring, SentimentScoringJob


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


def test_sentiment_scoring_job_updates_missing_sentiment_and_aggregates() -> None:
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
                    published_at=now - timedelta(hours=3),
                    source="marketaux_v1",
                    title="Apple beats expectations with strong growth",
                    sentiment_score=None,
                ),
                NewsEvent(
                    asset_id=aapl.id,
                    published_at=now - timedelta(hours=12),
                    source="marketaux_v1",
                    title="Analyst note",
                    sentiment_score=Decimal("-0.2000"),
                ),
            ]
        )
        session.commit()

    job = SentimentScoringJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        half_life_hours=24,
        source_filter="marketaux_v1",
    )
    result = job.run(now_utc=now)

    assert result.requested_assets == 2
    assert result.processed_assets == 2
    assert result.failed_assets == 0
    assert result.assets_without_articles == 1
    assert result.updated_articles == 1
    assert len(result.statuses) == 2

    aapl_status = next(item for item in result.statuses if item.symbol == "AAPL")
    assert aapl_status.article_count == 2
    assert aapl_status.scored_article_count == 2
    assert aapl_status.weighted_sentiment is not None
    assert aapl_status.normalized_score is not None

    with session_local() as session:
        updated_row = session.scalar(
            select(NewsEvent).where(
                NewsEvent.title == "Apple beats expectations with strong growth",
            )
        )
    assert updated_row is not None
    assert updated_row.sentiment_score is not None
    assert float(updated_row.sentiment_score) > 0.0
    assert isinstance(updated_row.details, dict)
    assert updated_row.details.get("sentiment_method") in {"lexicon", "blended"}


def test_sentiment_scoring_wrapper_skips_repeated_hourly_run() -> None:
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
                title="Apple strong profit beat",
                sentiment_score=None,
            )
        )
        session.commit()

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        sentiment_pipeline_symbol_limit=10,
        sentiment_pipeline_lookback_hours=72,
        sentiment_pipeline_half_life_hours=24,
        sentiment_pipeline_source_filter="marketaux_v1",
    )

    first = run_sentiment_scoring(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now,
    )
    second = run_sentiment_scoring(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now + timedelta(minutes=10),
    )

    assert first.idempotent_skip is False
    assert first.processed_assets == 1
    assert second.idempotent_skip is True
    assert second.processed_assets == 0
