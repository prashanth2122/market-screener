"""Main API router registration."""

from fastapi import APIRouter

from market_screener.api.routes import (
    alert_history,
    asset_detail,
    screener,
    system,
    watchlists,
)

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system")
api_router.include_router(screener.router, prefix="/screener")
api_router.include_router(asset_detail.router, prefix="/assets")
api_router.include_router(watchlists.router, prefix="/watchlists")
api_router.include_router(alert_history.router, prefix="/alerts")
