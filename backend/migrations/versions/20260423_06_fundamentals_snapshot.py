"""add fundamentals snapshot table

Revision ID: 20260423_06
Revises: 20260423_05
Create Date: 2026-04-23 19:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_06"
down_revision: Union[str, None] = "20260423_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fundamentals snapshot storage table."""

    op.create_table(
        "fundamentals_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("statement_currency", sa.String(length=10), nullable=True),
        sa.Column("revenue", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("gross_profit", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("ebit", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("net_income", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("operating_cash_flow", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("total_assets", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("total_liabilities", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("current_assets", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("current_liabilities", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("long_term_debt", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("retained_earnings", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("shares_outstanding", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("market_cap", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("eps_basic", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("eps_diluted", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "asset_id",
            "period_type",
            "period_end",
            "source",
            name="uq_fundamentals_snapshot_asset_period_source",
        ),
    )
    op.create_index(
        "ix_fundamentals_snapshot_asset_as_of",
        "fundamentals_snapshot",
        ["asset_id", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_fundamentals_snapshot_asset_period",
        "fundamentals_snapshot",
        ["asset_id", "period_type", "period_end"],
        unique=False,
    )


def downgrade() -> None:
    """Drop fundamentals snapshot storage table."""

    op.drop_index("ix_fundamentals_snapshot_asset_period", table_name="fundamentals_snapshot")
    op.drop_index("ix_fundamentals_snapshot_asset_as_of", table_name="fundamentals_snapshot")
    op.drop_table("fundamentals_snapshot")
