"""tune indexes for screener and detail endpoints

Revision ID: 20260428_11
Revises: 20260428_10
Create Date: 2026-04-28 00:00:01
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260428_11"
down_revision: Union[str, None] = "20260428_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_assets_active_type_exchange_quote",
        "assets",
        ["active", "asset_type", "exchange", "quote_currency"],
        unique=False,
    )

    op.create_index(
        "ix_signal_history_model_asset_asof",
        "signal_history",
        ["model_version", "asset_id", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_signal_history_asset_model_asof",
        "signal_history",
        ["asset_id", "model_version", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_score_history_asset_model_asof",
        "score_history",
        ["asset_id", "model_version", "as_of_ts"],
        unique=False,
    )

    op.create_index(
        "ix_prices_asset_source_ts",
        "prices",
        ["asset_id", "source", "ts"],
        unique=False,
    )
    op.create_index(
        "ix_indicators_snapshot_asset_source_ts",
        "indicators_snapshot",
        ["asset_id", "source", "ts"],
        unique=False,
    )
    op.create_index(
        "ix_fundamentals_snapshot_asset_source_period",
        "fundamentals_snapshot",
        ["asset_id", "source", "period_end", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_news_events_asset_source_published",
        "news_events",
        ["asset_id", "source", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_news_events_asset_source_published", table_name="news_events")
    op.drop_index(
        "ix_fundamentals_snapshot_asset_source_period", table_name="fundamentals_snapshot"
    )
    op.drop_index("ix_indicators_snapshot_asset_source_ts", table_name="indicators_snapshot")
    op.drop_index("ix_prices_asset_source_ts", table_name="prices")
    op.drop_index("ix_score_history_asset_model_asof", table_name="score_history")
    op.drop_index("ix_signal_history_asset_model_asof", table_name="signal_history")
    op.drop_index("ix_signal_history_model_asset_asof", table_name="signal_history")
    op.drop_index("ix_assets_active_type_exchange_quote", table_name="assets")
