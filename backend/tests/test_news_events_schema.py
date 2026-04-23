"""Tests for news events schema design constraints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, NewsEvent


def test_news_event_persists_expected_fields() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
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
            NewsEvent(
                asset_id=asset.id,
                published_at=datetime(2026, 4, 23, 8, 0, tzinfo=UTC),
                source="marketaux_v1",
                title="Apple expands AI roadmap",
                description="A short summary",
                url="https://example.com/apple-ai",
                language="en",
                sentiment_score=Decimal("0.4200"),
                event_type=None,
                risk_flag=None,
                details={"provider": "marketaux", "uuid": "article-1"},
            )
        )
        session.commit()

    with session_local() as session:
        row = session.scalar(select(NewsEvent))

    assert row is not None
    assert row.source == "marketaux_v1"
    assert row.language == "en"
    assert float(row.sentiment_score or 0) == 0.42
    assert row.details == {"provider": "marketaux", "uuid": "article-1"}


def test_news_event_unique_constraint_blocks_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    asset_id: int
    published = datetime(2026, 4, 23, 8, 0, tzinfo=UTC)
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
            NewsEvent(
                asset_id=asset.id,
                published_at=published,
                source="marketaux_v1",
                title="Microsoft earnings beat",
            )
        )
        session.commit()

    with session_local() as session:
        session.add(
            NewsEvent(
                asset_id=asset_id,
                published_at=published,
                source="marketaux_v1",
                title="Microsoft earnings beat",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_news_event_allows_same_article_title_across_different_sources() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    published = datetime(2026, 4, 23, 8, 0, tzinfo=UTC)
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
                NewsEvent(
                    asset_id=asset.id,
                    published_at=published,
                    source="marketaux_v1",
                    title="NVIDIA launches new chips",
                ),
                NewsEvent(
                    asset_id=asset.id,
                    published_at=published,
                    source="finnhub_news",
                    title="NVIDIA launches new chips",
                ),
            ]
        )
        session.commit()

    with session_local() as session:
        rows = session.scalars(select(NewsEvent)).all()
    assert len(rows) == 2
