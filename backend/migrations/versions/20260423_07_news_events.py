"""add news events table

Revision ID: 20260423_07
Revises: 20260423_06
Create Date: 2026-04-23 23:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_07"
down_revision: Union[str, None] = "20260423_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create news article/event storage table."""

    op.create_table(
        "news_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=True),
        sa.Column("risk_flag", sa.Boolean(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "asset_id",
            "published_at",
            "source",
            "title",
            name="uq_news_events_asset_published_source_title",
        ),
    )
    op.create_index(
        "ix_news_events_asset_published",
        "news_events",
        ["asset_id", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_news_events_source_published",
        "news_events",
        ["source", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop news article/event storage table."""

    op.drop_index("ix_news_events_source_published", table_name="news_events")
    op.drop_index("ix_news_events_asset_published", table_name="news_events")
    op.drop_table("news_events")
