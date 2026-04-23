"""add indicators snapshot table

Revision ID: 20260423_05
Revises: 20260423_04
Create Date: 2026-04-23 13:35:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_05"
down_revision: Union[str, None] = "20260423_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create technical-indicator snapshot table."""

    op.create_table(
        "indicators_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ma50", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("ma200", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("rsi14", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("macd", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("macd_signal", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("atr14", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("bb_upper", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("bb_lower", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "asset_id",
            "ts",
            "source",
            name="uq_indicators_snapshot_asset_ts_source",
        ),
    )
    op.create_index(
        "ix_indicators_snapshot_asset_ts",
        "indicators_snapshot",
        ["asset_id", "ts"],
        unique=False,
    )


def downgrade() -> None:
    """Drop technical-indicator snapshot table."""

    op.drop_index("ix_indicators_snapshot_asset_ts", table_name="indicators_snapshot")
    op.drop_table("indicators_snapshot")
