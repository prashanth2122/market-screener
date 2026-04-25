"""add watchlists and watchlist items tables

Revision ID: 20260424_09
Revises: 20260423_08
Create Date: 2026-04-24 00:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260424_09"
down_revision: Union[str, None] = "20260423_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create watchlist metadata and membership tables."""

    op.create_table(
        "watchlists",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_watchlists_name"),
    )
    op.create_index(
        "ix_watchlists_active_name",
        "watchlists",
        ["active", "name"],
        unique=False,
    )

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "watchlist_id",
            sa.BigInteger(),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("watchlist_id", "asset_id", name="uq_watchlist_items_watchlist_asset"),
    )
    op.create_index(
        "ix_watchlist_items_watchlist_added",
        "watchlist_items",
        ["watchlist_id", "added_at"],
        unique=False,
    )
    op.create_index("ix_watchlist_items_asset", "watchlist_items", ["asset_id"], unique=False)


def downgrade() -> None:
    """Drop watchlist metadata and membership tables."""

    op.drop_index("ix_watchlist_items_asset", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_watchlist_added", table_name="watchlist_items")
    op.drop_table("watchlist_items")

    op.drop_index("ix_watchlists_active_name", table_name="watchlists")
    op.drop_table("watchlists")
