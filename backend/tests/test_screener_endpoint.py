"""Tests for screener API endpoint filtering and pagination."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.db.models.core import Asset, ScoreHistory, SignalHistory
from market_screener.main import app

client = TestClient(app)


def _seed_row(
    session_local,
    *,
    symbol: str,
    asset_type: str,
    exchange: str,
    quote_currency: str,
    signal: str,
    score: Decimal,
    confidence: Decimal,
    blocked_by_risk: bool,
    as_of_ts: datetime,
) -> None:
    with session_local() as session:
        asset = Asset(
            symbol=symbol,
            asset_type=asset_type,
            exchange=exchange,
            quote_currency=quote_currency,
            active=True,
        )
        session.add(asset)
        session.flush()
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=as_of_ts,
                model_version="v1.0.0",
                signal=signal,
                score=score,
                confidence=confidence,
                blocked_by_risk=blocked_by_risk,
                reasons=["seeded"],
            )
        )
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=as_of_ts,
                model_version="v1.0.0",
                composite_score=score,
                technical_score=Decimal("60.0"),
                fundamental_score=Decimal("65.0"),
                sentiment_risk_score=Decimal("70.0"),
                details={"seed": True},
            )
        )
        session.commit()


def test_screener_endpoint_returns_latest_rows_default_sorted_by_score(monkeypatch) -> None:
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
    _seed_row(
        session_local,
        symbol="AAPL",
        asset_type="equity",
        exchange="US",
        quote_currency="USD",
        signal="buy",
        score=Decimal("76.20"),
        confidence=Decimal("0.70"),
        blocked_by_risk=False,
        as_of_ts=now,
    )
    _seed_row(
        session_local,
        symbol="BTC",
        asset_type="crypto",
        exchange="GLOBAL",
        quote_currency="USD",
        signal="strong_buy",
        score=Decimal("85.10"),
        confidence=Decimal("0.82"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(minutes=5),
    )

    monkeypatch.setattr(
        "market_screener.api.routes.screener.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get("/api/v1/screener")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["pagination"]["total"] == 2
    assert payload["pagination"]["returned"] == 2
    assert [item["symbol"] for item in payload["items"]] == ["BTC", "AAPL"]
    assert payload["items"][0]["signal"] == "strong_buy"


def test_screener_endpoint_applies_filters_sort_and_pagination(monkeypatch) -> None:
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
    _seed_row(
        session_local,
        symbol="AAPL",
        asset_type="equity",
        exchange="US",
        quote_currency="USD",
        signal="strong_buy",
        score=Decimal("88.00"),
        confidence=Decimal("0.84"),
        blocked_by_risk=False,
        as_of_ts=now,
    )
    _seed_row(
        session_local,
        symbol="MSFT",
        asset_type="equity",
        exchange="US",
        quote_currency="USD",
        signal="buy",
        score=Decimal("74.00"),
        confidence=Decimal("0.66"),
        blocked_by_risk=False,
        as_of_ts=now,
    )
    _seed_row(
        session_local,
        symbol="RELIANCE",
        asset_type="equity",
        exchange="NSE",
        quote_currency="INR",
        signal="buy",
        score=Decimal("79.00"),
        confidence=Decimal("0.72"),
        blocked_by_risk=True,
        as_of_ts=now,
    )
    _seed_row(
        session_local,
        symbol="BTC",
        asset_type="crypto",
        exchange="GLOBAL",
        quote_currency="USD",
        signal="strong_buy",
        score=Decimal("90.00"),
        confidence=Decimal("0.90"),
        blocked_by_risk=False,
        as_of_ts=now,
    )

    monkeypatch.setattr(
        "market_screener.api.routes.screener.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get(
        "/api/v1/screener?"
        "asset_types=equity&exchanges=US&signals=strong_buy,buy"
        "&min_score=70&blocked_by_risk=false&sort_by=symbol&sort_dir=asc&limit=1&offset=1"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["pagination"]["total"] == 2
    assert payload["pagination"]["limit"] == 1
    assert payload["pagination"]["offset"] == 1
    assert payload["pagination"]["returned"] == 1
    assert payload["items"][0]["symbol"] == "MSFT"


def test_screener_endpoint_supports_symbol_query_and_confidence_filter(monkeypatch) -> None:
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
    _seed_row(
        session_local,
        symbol="AAPL",
        asset_type="equity",
        exchange="US",
        quote_currency="USD",
        signal="buy",
        score=Decimal("76.00"),
        confidence=Decimal("0.65"),
        blocked_by_risk=False,
        as_of_ts=now,
    )
    _seed_row(
        session_local,
        symbol="AAP",
        asset_type="equity",
        exchange="US",
        quote_currency="USD",
        signal="buy",
        score=Decimal("77.00"),
        confidence=Decimal("0.82"),
        blocked_by_risk=False,
        as_of_ts=now,
    )

    monkeypatch.setattr(
        "market_screener.api.routes.screener.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get("/api/v1/screener?symbol_query=aap&min_confidence=0.8")
    assert response.status_code == 200

    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["items"][0]["symbol"] == "AAP"
    assert payload["items"][0]["confidence"] == 0.82
