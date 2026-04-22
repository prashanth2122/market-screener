"""Main API router registration."""

from fastapi import APIRouter

from market_screener.api.routes import system

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system")
