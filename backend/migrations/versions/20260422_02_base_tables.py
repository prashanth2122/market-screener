"""create base tables

Revision ID: 20260422_02
Revises: 20260422_01
Create Date: 2026-04-22 22:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260422_02"
down_revision: Union[str, None] = "20260422_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial operational tables."""

    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("base_currency", sa.String(length=10), nullable=True),
        sa.Column("quote_currency", sa.String(length=10), nullable=False),
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
        sa.UniqueConstraint("symbol", name="uq_assets_symbol"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("run_id", name="uq_jobs_run_id"),
    )
    op.create_index("ix_jobs_name_started_at", "jobs", ["job_name", "started_at"], unique=False)

    op.create_table(
        "provider_health",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("quota_remaining", sa.Integer(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("provider_name", "ts", name="uq_provider_health_provider_ts"),
    )
    op.create_index(
        "ix_provider_health_provider_ts",
        "provider_health",
        ["provider_name", "ts"],
        unique=False,
    )

    op.create_table(
        "prices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ingest_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_prices_asset_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("asset_id", "ts", "source", name="uq_prices_asset_ts_source"),
    )
    op.create_index("ix_prices_asset_ts", "prices", ["asset_id", "ts"], unique=False)


def downgrade() -> None:
    """Drop initial operational tables."""

    op.drop_index("ix_prices_asset_ts", table_name="prices")
    op.drop_table("prices")

    op.drop_index("ix_provider_health_provider_ts", table_name="provider_health")
    op.drop_table("provider_health")

    op.drop_index("ix_jobs_name_started_at", table_name="jobs")
    op.drop_table("jobs")

    op.drop_table("assets")
