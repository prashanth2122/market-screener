"""Watchlist CRUD API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, Watchlist, WatchlistItem
from market_screener.db.session import create_session_factory_from_settings

router = APIRouter(tags=["watchlists"])


class CreateWatchlistRequest(BaseModel):
    """Payload for creating a watchlist."""

    name: str
    description: str | None = None
    active: bool = True


class UpdateWatchlistRequest(BaseModel):
    """Payload for updating watchlist metadata."""

    name: str | None = None
    description: str | None = None
    active: bool | None = None


class AddWatchlistItemRequest(BaseModel):
    """Payload for adding an asset to a watchlist."""

    symbol: str
    notes: str | None = None


@router.get("")
def list_watchlists(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """List all watchlists with item counts."""

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        rows = session.execute(
            select(Watchlist, func.count(WatchlistItem.id).label("item_count"))
            .outerjoin(WatchlistItem, WatchlistItem.watchlist_id == Watchlist.id)
            .group_by(Watchlist.id)
            .order_by(Watchlist.name.asc())
        ).all()

    items = [
        {
            "id": row[0].id,
            "name": row[0].name,
            "description": row[0].description,
            "active": bool(row[0].active),
            "item_count": int(row[1] or 0),
            "created_at": normalize_to_utc(row[0].created_at).isoformat(),
            "updated_at": normalize_to_utc(row[0].updated_at).isoformat(),
        }
        for row in rows
    ]
    return {
        "status": "ok",
        "total": len(items),
        "items": items,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_watchlist(
    payload: CreateWatchlistRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Create a new watchlist."""

    normalized_name = (payload.name or "").strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="watchlist name is required",
        )

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        existing = session.scalar(
            select(Watchlist).where(func.lower(Watchlist.name) == normalized_name.lower()).limit(1)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"watchlist already exists: {normalized_name}",
            )

        now = datetime.now(UTC)
        row = Watchlist(
            name=normalized_name,
            description=(payload.description or "").strip() or None,
            active=payload.active,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

    return {
        "status": "ok",
        "watchlist": {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "active": bool(row.active),
            "created_at": normalize_to_utc(row.created_at).isoformat(),
            "updated_at": normalize_to_utc(row.updated_at).isoformat(),
        },
    }


@router.get("/{watchlist_id}")
def get_watchlist(
    watchlist_id: int = Path(ge=1),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return watchlist metadata and member assets."""

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        watchlist = session.scalar(select(Watchlist).where(Watchlist.id == watchlist_id).limit(1))
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist not found: {watchlist_id}",
            )

        rows = session.execute(
            select(WatchlistItem, Asset)
            .join(Asset, Asset.id == WatchlistItem.asset_id)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.added_at.desc(), Asset.symbol.asc())
        ).all()

    items = [
        {
            "id": row[0].id,
            "symbol": row[1].symbol,
            "asset_type": row[1].asset_type,
            "exchange": row[1].exchange,
            "quote_currency": row[1].quote_currency,
            "notes": row[0].notes,
            "added_at": normalize_to_utc(row[0].added_at).isoformat(),
        }
        for row in rows
    ]
    return {
        "status": "ok",
        "watchlist": {
            "id": watchlist.id,
            "name": watchlist.name,
            "description": watchlist.description,
            "active": bool(watchlist.active),
            "created_at": normalize_to_utc(watchlist.created_at).isoformat(),
            "updated_at": normalize_to_utc(watchlist.updated_at).isoformat(),
        },
        "item_count": len(items),
        "items": items,
    }


@router.patch("/{watchlist_id}")
def update_watchlist(
    payload: UpdateWatchlistRequest,
    watchlist_id: int = Path(ge=1),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Update watchlist metadata fields."""

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        watchlist = session.scalar(select(Watchlist).where(Watchlist.id == watchlist_id).limit(1))
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist not found: {watchlist_id}",
            )

        if payload.name is not None:
            normalized_name = payload.name.strip()
            if not normalized_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="watchlist name cannot be empty",
                )
            duplicate = session.scalar(
                select(Watchlist)
                .where(
                    func.lower(Watchlist.name) == normalized_name.lower(),
                    Watchlist.id != watchlist_id,
                )
                .limit(1)
            )
            if duplicate is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"watchlist already exists: {normalized_name}",
                )
            watchlist.name = normalized_name
        if payload.description is not None:
            watchlist.description = (payload.description or "").strip() or None
        if payload.active is not None:
            watchlist.active = payload.active

        watchlist.updated_at = datetime.now(UTC)
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)

    return {
        "status": "ok",
        "watchlist": {
            "id": watchlist.id,
            "name": watchlist.name,
            "description": watchlist.description,
            "active": bool(watchlist.active),
            "created_at": normalize_to_utc(watchlist.created_at).isoformat(),
            "updated_at": normalize_to_utc(watchlist.updated_at).isoformat(),
        },
    }


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int = Path(ge=1),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Delete one watchlist and its member rows."""

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        watchlist = session.scalar(select(Watchlist).where(Watchlist.id == watchlist_id).limit(1))
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist not found: {watchlist_id}",
            )
        session.delete(watchlist)
        session.commit()

    return {
        "status": "ok",
        "deleted": True,
        "watchlist_id": watchlist_id,
    }


@router.post("/{watchlist_id}/items")
def add_watchlist_item(
    payload: AddWatchlistItemRequest,
    watchlist_id: int = Path(ge=1),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Add an asset symbol into the target watchlist."""

    normalized_symbol = (payload.symbol or "").strip().upper()
    if not normalized_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbol is required",
        )

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        watchlist = session.scalar(select(Watchlist).where(Watchlist.id == watchlist_id).limit(1))
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist not found: {watchlist_id}",
            )
        asset = session.scalar(
            select(Asset).where(func.upper(Asset.symbol) == normalized_symbol).limit(1)
        )
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset not found: {normalized_symbol}",
            )

        existing = session.scalar(
            select(WatchlistItem)
            .where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.asset_id == asset.id,
            )
            .limit(1)
        )
        if existing is not None:
            if payload.notes is not None:
                existing.notes = (payload.notes or "").strip() or None
                session.add(existing)
                session.commit()
                session.refresh(existing)
            return {
                "status": "ok",
                "added": False,
                "item": {
                    "id": existing.id,
                    "watchlist_id": watchlist_id,
                    "symbol": asset.symbol,
                    "notes": existing.notes,
                    "added_at": normalize_to_utc(existing.added_at).isoformat(),
                },
            }

        now = datetime.now(UTC)
        row = WatchlistItem(
            watchlist_id=watchlist_id,
            asset_id=asset.id,
            notes=(payload.notes or "").strip() or None,
            added_at=now,
            created_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"watchlist item already exists: {normalized_symbol}",
            ) from exc
        session.refresh(row)

    return {
        "status": "ok",
        "added": True,
        "item": {
            "id": row.id,
            "watchlist_id": watchlist_id,
            "symbol": normalized_symbol,
            "notes": row.notes,
            "added_at": normalize_to_utc(row.added_at).isoformat(),
        },
    }


@router.delete("/{watchlist_id}/items/{symbol}")
def delete_watchlist_item(
    watchlist_id: int = Path(ge=1),
    symbol: str = Path(min_length=1),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Delete one watchlist item by symbol."""

    normalized_symbol = symbol.strip().upper()
    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        watchlist = session.scalar(select(Watchlist).where(Watchlist.id == watchlist_id).limit(1))
        if watchlist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist not found: {watchlist_id}",
            )

        row = session.scalar(
            select(WatchlistItem)
            .join(Asset, Asset.id == WatchlistItem.asset_id)
            .where(
                WatchlistItem.watchlist_id == watchlist_id,
                func.upper(Asset.symbol) == normalized_symbol,
            )
            .limit(1)
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"watchlist item not found: {normalized_symbol}",
            )

        session.delete(row)
        session.commit()

    return {
        "status": "ok",
        "deleted": True,
        "watchlist_id": watchlist_id,
        "symbol": normalized_symbol,
    }


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
