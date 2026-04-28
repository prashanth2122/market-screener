"""End-to-end tests for core API flows (Day 81)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    Job,
    NewsEvent,
    Price,
    ScoreHistory,
    SignalHistory,
    Watchlist,
    WatchlistItem,
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
    Job.__table__.create(engine)
    Watchlist.__table__.create(engine)
    WatchlistItem.__table__.create(engine)

    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_core_flow_screener_to_asset_detail_to_watchlist_and_alert_history(monkeypatch) -> None:
    session_local = _build_session_factory()
    now = datetime.now(UTC)
    as_of = now - timedelta(minutes=10)

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
                ScoreHistory(
                    asset_id=aapl.id,
                    as_of_ts=as_of,
                    model_version="v1.0.1",
                    composite_score=Decimal("82.20"),
                    technical_score=Decimal("80.00"),
                    fundamental_score=Decimal("78.00"),
                    sentiment_risk_score=Decimal("88.00"),
                    details={
                        "effective_weights": {
                            "technical_strength": 0.5,
                            "fundamental_quality": 0.3,
                            "sentiment_event_risk": 0.2,
                        },
                        "unavailable_components": [],
                    },
                ),
                SignalHistory(
                    asset_id=aapl.id,
                    as_of_ts=as_of,
                    model_version="v1.0.1",
                    signal="strong_buy",
                    score=Decimal("82.20"),
                    confidence=Decimal("0.83"),
                    blocked_by_risk=False,
                    reasons=["trend_support"],
                    details={"label": "Strong Buy", "score_band": "high"},
                ),
                SignalHistory(
                    asset_id=btc.id,
                    as_of_ts=as_of,
                    model_version="v1.0.1",
                    signal="watch",
                    score=Decimal("61.00"),
                    confidence=Decimal("0.62"),
                    blocked_by_risk=False,
                    reasons=["mixed_context"],
                ),
            ]
        )

        session.add_all(
            [
                Price(
                    asset_id=aapl.id,
                    ts=as_of - timedelta(days=2),
                    open=Decimal("100"),
                    high=Decimal("105"),
                    low=Decimal("99"),
                    close=Decimal("104"),
                    volume=Decimal("1000"),
                    source="finnhub",
                ),
                Price(
                    asset_id=aapl.id,
                    ts=as_of - timedelta(days=1),
                    open=Decimal("104"),
                    high=Decimal("106"),
                    low=Decimal("103"),
                    close=Decimal("105"),
                    volume=Decimal("1200"),
                    source="finnhub",
                ),
                Price(
                    asset_id=aapl.id,
                    ts=as_of,
                    open=Decimal("105"),
                    high=Decimal("108"),
                    low=Decimal("104"),
                    close=Decimal("107"),
                    volume=Decimal("1400"),
                    source="finnhub",
                ),
            ]
        )
        session.add(
            IndicatorSnapshot(
                asset_id=aapl.id,
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
                asset_id=aapl.id,
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
        session.add_all(
            [
                NewsEvent(
                    asset_id=aapl.id,
                    published_at=as_of - timedelta(hours=3),
                    source="marketaux_v1",
                    title="AAPL expands enterprise distribution",
                    description="New partner rollout widens reach.",
                    url="https://example.test/aapl-news",
                    language="en",
                    sentiment_score=Decimal("0.28"),
                    event_type="earnings",
                    risk_flag=False,
                ),
                NewsEvent(
                    asset_id=aapl.id,
                    published_at=as_of - timedelta(hours=1),
                    source="marketaux_v1",
                    title="AAPL supply chain jitters",
                    description="Short-term delay risk flagged by analysts.",
                    url="https://example.test/aapl-risk",
                    language="en",
                    sentiment_score=Decimal("-0.32"),
                    event_type="supply_chain",
                    risk_flag=True,
                ),
            ]
        )
        session.add(
            Job(
                job_name="telegram_alert_dispatch",
                run_id="run-telegram-1",
                idempotency_key="e2e",
                status="completed",
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
                details={
                    "sent_alerts": [
                        {
                            "symbol": "AAPL",
                            "as_of_ts": as_of.isoformat(),
                            "sent_at": (now - timedelta(minutes=5)).isoformat(),
                        }
                    ]
                },
            )
        )
        session.commit()

    for module_path in (
        "market_screener.api.routes.screener",
        "market_screener.api.routes.asset_detail",
        "market_screener.api.routes.watchlists",
        "market_screener.api.routes.alert_history",
    ):
        monkeypatch.setattr(
            f"{module_path}.create_session_factory_from_settings",
            lambda _settings, _session_local=session_local: _session_local,
        )

    screener = client.get("/api/v1/screener?asset_types=equity&min_score=70")
    assert screener.status_code == 200
    screener_payload = screener.json()
    assert screener_payload["status"] == "ok"
    assert screener_payload["pagination"]["total"] == 1
    assert screener_payload["items"][0]["symbol"] == "AAPL"

    detail = client.get("/api/v1/assets/AAPL?price_limit=200&news_limit=5")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "ok"
    assert detail_payload["asset"]["symbol"] == "AAPL"
    assert detail_payload["counts"]["prices"] >= 3
    assert detail_payload["counts"]["news"] == 2
    assert (
        detail_payload["history"]["prices"][0]["ts"] < detail_payload["history"]["prices"][-1]["ts"]
    )
    assert detail_payload["history"]["news"][0]["title"]

    created = client.post("/api/v1/watchlists", json={"name": "Core Flow", "description": "e2e"})
    assert created.status_code == 201
    watchlist_id = created.json()["watchlist"]["id"]
    assert watchlist_id >= 1

    added = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "AAPL", "notes": "watch"},
    )
    assert added.status_code == 200
    assert added.json()["item"]["symbol"] == "AAPL"

    read_back = client.get(f"/api/v1/watchlists/{watchlist_id}")
    assert read_back.status_code == 200
    read_payload = read_back.json()
    assert read_payload["watchlist"]["name"] == "Core Flow"
    assert len(read_payload["items"]) == 1
    assert read_payload["items"][0]["symbol"] == "AAPL"

    history = client.get("/api/v1/alerts/history?channel=telegram&since_hours=48")
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["status"] == "ok"
    assert history_payload["pagination"]["total"] == 1
    assert history_payload["items"][0]["symbol"] == "AAPL"
