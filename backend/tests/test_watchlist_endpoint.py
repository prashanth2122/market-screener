"""Tests for watchlist CRUD API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.db.models.core import Asset, Watchlist, WatchlistItem
from market_screener.main import app

client = TestClient(app)


def _build_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    Watchlist.__table__.create(engine)
    WatchlistItem.__table__.create(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_watchlist_crud_metadata_flow(monkeypatch) -> None:
    session_local = _build_session_factory()
    monkeypatch.setattr(
        "market_screener.api.routes.watchlists.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    create_response = client.post(
        "/api/v1/watchlists",
        json={"name": "Core Swing", "description": "Primary swing list", "active": True},
    )
    assert create_response.status_code == 201
    watchlist_id = create_response.json()["watchlist"]["id"]

    list_response = client.get("/api/v1/watchlists")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["item_count"] == 0

    update_response = client.patch(
        f"/api/v1/watchlists/{watchlist_id}",
        json={"description": "Updated desc", "active": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["watchlist"]["description"] == "Updated desc"
    assert update_response.json()["watchlist"]["active"] is False

    detail_response = client.get(f"/api/v1/watchlists/{watchlist_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["watchlist"]["name"] == "Core Swing"
    assert detail_response.json()["item_count"] == 0

    delete_response = client.delete(f"/api/v1/watchlists/{watchlist_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    final_list = client.get("/api/v1/watchlists")
    assert final_list.status_code == 200
    assert final_list.json()["total"] == 0


def test_watchlist_item_add_remove_and_duplicate_behavior(monkeypatch) -> None:
    session_local = _build_session_factory()
    with session_local() as session:
        session.add_all(
            [
                Asset(
                    symbol="AAPL",
                    asset_type="equity",
                    exchange="US",
                    quote_currency="USD",
                    active=True,
                ),
                Asset(
                    symbol="BTC",
                    asset_type="crypto",
                    exchange="GLOBAL",
                    quote_currency="USD",
                    active=True,
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "market_screener.api.routes.watchlists.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    create_response = client.post("/api/v1/watchlists", json={"name": "Momentum"})
    assert create_response.status_code == 201
    watchlist_id = create_response.json()["watchlist"]["id"]

    add_first = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "aapl", "notes": "First add"},
    )
    assert add_first.status_code == 200
    assert add_first.json()["added"] is True
    assert add_first.json()["item"]["symbol"] == "AAPL"

    add_duplicate = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "AAPL", "notes": "Updated note"},
    )
    assert add_duplicate.status_code == 200
    assert add_duplicate.json()["added"] is False
    assert add_duplicate.json()["item"]["notes"] == "Updated note"

    detail_response = client.get(f"/api/v1/watchlists/{watchlist_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["item_count"] == 1
    assert detail_response.json()["items"][0]["symbol"] == "AAPL"
    assert detail_response.json()["items"][0]["notes"] == "Updated note"

    delete_item = client.delete(f"/api/v1/watchlists/{watchlist_id}/items/AAPL")
    assert delete_item.status_code == 200
    assert delete_item.json()["deleted"] is True

    detail_after_delete = client.get(f"/api/v1/watchlists/{watchlist_id}")
    assert detail_after_delete.status_code == 200
    assert detail_after_delete.json()["item_count"] == 0


def test_watchlist_error_paths(monkeypatch) -> None:
    session_local = _build_session_factory()
    with session_local() as session:
        session.add(
            Asset(
                symbol="AAPL",
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    monkeypatch.setattr(
        "market_screener.api.routes.watchlists.create_session_factory_from_settings",
        lambda _settings: session_local,
    )

    missing_watchlist = client.get("/api/v1/watchlists/99")
    assert missing_watchlist.status_code == 404

    create_one = client.post("/api/v1/watchlists", json={"name": "Alpha"})
    assert create_one.status_code == 201
    watchlist_id = create_one.json()["watchlist"]["id"]

    duplicate_name = client.post("/api/v1/watchlists", json={"name": "alpha"})
    assert duplicate_name.status_code == 409

    unknown_symbol = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "UNKNOWN"},
    )
    assert unknown_symbol.status_code == 404

    missing_item = client.delete(f"/api/v1/watchlists/{watchlist_id}/items/AAPL")
    assert missing_item.status_code == 404
