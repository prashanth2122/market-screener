"""Integration tests covering sentiment and event-risk pipelines together."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, NewsEvent
from market_screener.jobs.event_risk_tagging import EventRiskTaggingJob
from market_screener.jobs.sentiment_scoring import SentimentScoringJob


def test_sentiment_backfill_drives_sentiment_shock_event_tag() -> None:
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
                title="Demand outlook weak as losses deepen",
                description="Negative tone continues across guidance update.",
                sentiment_score=None,
                event_type=None,
                risk_flag=None,
                details={"existing_key": "existing_value"},
            )
        )
        session.commit()

    sentiment_job = SentimentScoringJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        half_life_hours=24,
        source_filter="marketaux_v1",
    )
    sentiment_result = sentiment_job.run(now_utc=now)
    assert sentiment_result.processed_assets == 1
    assert sentiment_result.updated_articles == 1

    event_job = EventRiskTaggingJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        source_filter="marketaux_v1",
        negative_sentiment_threshold=-0.35,
    )
    event_result = event_job.run(now_utc=now)
    assert event_result.processed_assets == 1
    assert event_result.articles_updated == 1
    assert event_result.high_risk_articles == 1

    with session_local() as session:
        row = session.scalar(select(NewsEvent))
    assert row is not None
    assert row.sentiment_score is not None
    assert float(row.sentiment_score) <= -0.35
    assert row.event_type == "sentiment_shock"
    assert row.risk_flag is True
    assert isinstance(row.details, dict)
    assert row.details.get("existing_key") == "existing_value"
    assert row.details.get("sentiment_method") in {"lexicon", "blended"}
    assert row.details.get("event_risk_sentiment_triggered") is True


def test_keyword_event_risk_tagging_overrides_positive_sentiment_context() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    with session_local() as session:
        msft = Asset(
            symbol="MSFT",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(msft)
        session.flush()
        session.add(
            NewsEvent(
                asset_id=msft.id,
                published_at=now - timedelta(hours=1),
                source="marketaux_v1",
                title="Company beats estimates but faces SEC probe",
                description="Strong quarter reported despite regulatory pressure.",
                sentiment_score=Decimal("0.9000"),
                event_type=None,
                risk_flag=None,
                details={},
            )
        )
        session.commit()

    sentiment_job = SentimentScoringJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        half_life_hours=24,
        source_filter="marketaux_v1",
    )
    sentiment_result = sentiment_job.run(now_utc=now)
    assert sentiment_result.processed_assets == 1
    assert sentiment_result.updated_articles == 0

    event_job = EventRiskTaggingJob(
        session_local,
        symbol_limit=10,
        lookback_hours=72,
        source_filter="marketaux_v1",
        negative_sentiment_threshold=-0.35,
    )
    event_result = event_job.run(now_utc=now)
    assert event_result.processed_assets == 1
    assert event_result.high_risk_articles == 1

    with session_local() as session:
        row = session.scalar(select(NewsEvent))
    assert row is not None
    assert float(row.sentiment_score or Decimal("0")) > 0.0
    assert row.event_type == "regulatory"
    assert row.risk_flag is True
    assert isinstance(row.details, dict)
    assert row.details.get("event_risk_sentiment_triggered") is False
    assert "keyword:regulatory" in (row.details.get("event_risk_rule_hits") or [])
