"""add score and signal history tables

Revision ID: 20260423_08
Revises: 20260423_07
Create Date: 2026-04-23 23:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_08"
down_revision: Union[str, None] = "20260423_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create score and signal history storage tables."""

    op.create_table(
        "score_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("composite_score", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("technical_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("fundamental_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("sentiment_risk_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "asset_id",
            "as_of_ts",
            "model_version",
            name="uq_score_history_asset_asof_model",
        ),
    )
    op.create_index(
        "ix_score_history_asset_asof",
        "score_history",
        ["asset_id", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_score_history_model_asof",
        "score_history",
        ["model_version", "as_of_ts"],
        unique=False,
    )

    op.create_table(
        "signal_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("blocked_by_risk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "asset_id",
            "as_of_ts",
            "model_version",
            name="uq_signal_history_asset_asof_model",
        ),
    )
    op.create_index(
        "ix_signal_history_asset_asof",
        "signal_history",
        ["asset_id", "as_of_ts"],
        unique=False,
    )
    op.create_index(
        "ix_signal_history_signal_asof",
        "signal_history",
        ["signal", "as_of_ts"],
        unique=False,
    )


def downgrade() -> None:
    """Drop score and signal history storage tables."""

    op.drop_index("ix_signal_history_signal_asof", table_name="signal_history")
    op.drop_index("ix_signal_history_asset_asof", table_name="signal_history")
    op.drop_table("signal_history")

    op.drop_index("ix_score_history_model_asof", table_name="score_history")
    op.drop_index("ix_score_history_asset_asof", table_name="score_history")
    op.drop_table("score_history")
