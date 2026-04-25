"""Import ORM models here so Alembic autogenerate can discover metadata."""

from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    IngestionFailure,
    Job,
    NewsEvent,
    Price,
    ProviderHealth,
    ScoreHistory,
    SignalHistory,
    Watchlist,
    WatchlistItem,
)

__all__ = [
    "Asset",
    "Price",
    "Job",
    "ProviderHealth",
    "IngestionFailure",
    "IndicatorSnapshot",
    "FundamentalsSnapshot",
    "NewsEvent",
    "ScoreHistory",
    "SignalHistory",
    "Watchlist",
    "WatchlistItem",
]
