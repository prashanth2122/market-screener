"""Tests for asset detail API endpoint behavior."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _build_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    IndicatorSnapshot.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_asset_detail_endpoint_returns_latest_context_and_history(monkeypatch) -> None:
    session_local = _build_session_factory()
    as_of = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
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
                    ts=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=Decimal("1000"),
                    source="finnhub",
                ),
                Price(
                    asset_id=asset.id,
                    ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                    open=Decimal("101"),
                    high=Decimal("103"),
                    low=Decimal("100"),
                    close=Decimal("102"),
                    volume=Decimal("1200"),
                    source="finnhub",
                ),
            ]
        )
        session.add(
            IndicatorSnapshot(
                asset_id=asset.id,
                ts=as_of,
                ma50=Decimal("99"),
                ma200=Decimal("95"),
                rsi14=Decimal("57"),
                macd=Decimal("1.2"),
                macd_signal=Decimal("0.9"),
                atr14=Decimal("2.2"),
                bb_upper=Decimal("106"),
                bb_lower=Decimal("94"),
                source="ta_v1",
            )
        )
        session.add(
            FundamentalsSnapshot(
                asset_id=asset.id,
                as_of_ts=as_of,
                period_type="annual",
                period_end=date(2025, 12, 31),
                filing_date=date(2026, 2, 5),
                statement_currency="USD",
                revenue=Decimal("1200"),
                gross_profit=Decimal("500"),
                ebit=Decimal("180"),
                net_income=Decimal("140"),
                operating_cash_flow=Decimal("165"),
                total_assets=Decimal("950"),
                total_liabilities=Decimal("520"),
                market_cap=Decimal("1800"),
                eps_basic=Decimal("2.7"),
                eps_diluted=Decimal("2.6"),
                source="fmp_v1",
            )
        )
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.0",
                composite_score=Decimal("81.5"),
                technical_score=Decimal("79.0"),
                fundamental_score=Decimal("82.0"),
                sentiment_risk_score=Decimal("84.0"),
            )
        )
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.0",
                signal="strong_buy",
                score=Decimal("81.5"),
                confidence=Decimal("0.82"),
                blocked_by_risk=False,
                reasons=["trend_support"],
            )
        )
        session.add(
            NewsEvent(
                asset_id=asset.id,
                published_at=as_of,
                source="marketaux_v1",
                title="AAPL expands enterprise distribution",
                sentiment_score=Decimal("0.35"),
                event_type="earnings",
                risk_flag=False,
            )
        )
        session.commit()

    monkeypatch.setattr(
        "market_screener.api.routes.asset_detail.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get("/api/v1/assets/AAPL")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["asset"]["symbol"] == "AAPL"
    assert payload["latest"]["signal"]["signal"] == "strong_buy"
    assert payload["latest"]["score"]["composite_score"] == 81.5
    assert payload["latest"]["indicator"]["source"] == "ta_v1"
    assert payload["latest"]["fundamentals"]["period_end"] == "2025-12-31"
    assert payload["counts"]["prices"] == 2
    assert payload["counts"]["news"] == 1
    assert payload["history"]["prices"][0]["ts"] < payload["history"]["prices"][1]["ts"]


def test_asset_detail_endpoint_applies_source_and_limit_filters(monkeypatch) -> None:
    session_local = _build_session_factory()
    as_of = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    with session_local() as session:
        asset = Asset(
            symbol="BTC",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        session.add_all(
            [
                Price(
                    asset_id=asset.id,
                    ts=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
                    open=Decimal("70000"),
                    high=Decimal("71000"),
                    low=Decimal("69000"),
                    close=Decimal("70500"),
                    volume=Decimal("150"),
                    source="coingecko",
                ),
                Price(
                    asset_id=asset.id,
                    ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                    open=Decimal("70500"),
                    high=Decimal("71500"),
                    low=Decimal("70000"),
                    close=Decimal("71000"),
                    volume=Decimal("170"),
                    source="exchange",
                ),
            ]
        )
        session.add_all(
            [
                NewsEvent(
                    asset_id=asset.id,
                    published_at=as_of,
                    source="marketaux_v1",
                    title="BTC sees inflow",
                    sentiment_score=Decimal("0.25"),
                ),
                NewsEvent(
                    asset_id=asset.id,
                    published_at=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
                    source="other_wire",
                    title="BTC correction risk",
                    sentiment_score=Decimal("-0.10"),
                ),
            ]
        )
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.0",
                signal="buy",
                score=Decimal("74"),
                confidence=Decimal("0.73"),
                blocked_by_risk=False,
                reasons=["momentum"],
            )
        )
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.0",
                composite_score=Decimal("74"),
            )
        )
        session.commit()

    monkeypatch.setattr(
        "market_screener.api.routes.asset_detail.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get(
        "/api/v1/assets/BTC?"
        "price_source=coingecko&price_limit=1&news_source=marketaux_v1&news_limit=1"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["prices"] == 1
    assert payload["history"]["prices"][0]["source"] == "coingecko"
    assert payload["counts"]["news"] == 1
    assert payload["history"]["news"][0]["source"] == "marketaux_v1"


def test_asset_detail_endpoint_returns_404_for_unknown_symbol(monkeypatch) -> None:
    session_local = _build_session_factory()
    monkeypatch.setattr(
        "market_screener.api.routes.asset_detail.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    response = client.get("/api/v1/assets/UNKNOWN")
    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found: UNKNOWN"
