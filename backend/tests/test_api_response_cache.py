"""End-to-end-ish tests for API response caching on hot dashboard endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.api.cache_helpers import get_api_cache
from market_screener.core.settings import get_settings
from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    NewsEvent,
    Price,
    ScoreHistory,
    SignalHistory,
)
from market_screener.main import app

client = TestClient(app)


def test_screener_response_is_cached(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
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
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=now,
                model_version="v1.0.1",
                signal="buy",
                score=Decimal("76.20"),
                confidence=Decimal("0.70"),
                blocked_by_risk=False,
                reasons=["seeded"],
            )
        )
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=now,
                model_version="v1.0.1",
                composite_score=Decimal("76.20"),
                technical_score=Decimal("60.0"),
                fundamental_score=Decimal("65.0"),
                sentiment_risk_score=Decimal("70.0"),
                details={"seed": True},
            )
        )
        session.commit()

    call_count = {"count": 0}

    def _factory(_settings):
        call_count["count"] += 1
        return session_local

    monkeypatch.setattr(
        "market_screener.api.routes.screener.create_session_factory_from_settings",
        _factory,
    )

    settings = get_settings()
    get_api_cache(max_entries=settings.api_cache_max_entries).clear()

    first = client.get("/api/v1/screener?limit=10")
    assert first.status_code == 200
    assert first.headers.get("X-Cache") == "MISS"
    assert call_count["count"] == 1

    second = client.get("/api/v1/screener?limit=10")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"
    assert call_count["count"] == 1


def test_asset_detail_response_is_cached(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    Price.__table__.create(engine)
    NewsEvent.__table__.create(engine)
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
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=now,
                model_version="v1.0.1",
                signal="buy",
                score=Decimal("76.20"),
                confidence=Decimal("0.70"),
                blocked_by_risk=False,
                reasons=["seeded"],
            )
        )
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=now,
                model_version="v1.0.1",
                composite_score=Decimal("76.20"),
                technical_score=Decimal("60.0"),
                fundamental_score=Decimal("65.0"),
                sentiment_risk_score=Decimal("70.0"),
                details={"seed": True},
            )
        )
        session.commit()

    call_count = {"count": 0}

    def _factory(_settings):
        call_count["count"] += 1
        return session_local

    monkeypatch.setattr(
        "market_screener.api.routes.asset_detail.create_session_factory_from_settings",
        _factory,
    )

    settings = get_settings()
    get_api_cache(max_entries=settings.api_cache_max_entries).clear()

    first = client.get("/api/v1/assets/AAPL?price_limit=5&price_lookback_days=1")
    assert first.status_code == 200
    assert first.headers.get("X-Cache") == "MISS"
    assert call_count["count"] == 1

    second = client.get("/api/v1/assets/AAPL?price_limit=5&price_lookback_days=1")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"
    assert call_count["count"] == 1
