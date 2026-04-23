"""Import ORM models here so Alembic autogenerate can discover metadata."""

from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    IngestionFailure,
    Job,
    Price,
    ProviderHealth,
)

__all__ = [
    "Asset",
    "Price",
    "Job",
    "ProviderHealth",
    "IngestionFailure",
    "IndicatorSnapshot",
    "FundamentalsSnapshot",
]
