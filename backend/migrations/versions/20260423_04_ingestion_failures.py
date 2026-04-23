"""add ingestion failures table

Revision ID: 20260423_04
Revises: 20260423_03
Create Date: 2026-04-23 02:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_04"
down_revision: Union[str, None] = "20260423_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ingestion failure tracking table for retries."""

    op.create_table(
        "ingestion_failures",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("failure_key", sa.String(length=160), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("asset_symbol", sa.String(length=32), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("failure_key", name="uq_ingestion_failures_failure_key"),
    )
    op.create_index(
        "ix_ingestion_failures_status_next_retry",
        "ingestion_failures",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_failures_job_symbol",
        "ingestion_failures",
        ["job_name", "asset_symbol"],
        unique=False,
    )


def downgrade() -> None:
    """Drop ingestion failure tracking table."""

    op.drop_index("ix_ingestion_failures_job_symbol", table_name="ingestion_failures")
    op.drop_index("ix_ingestion_failures_status_next_retry", table_name="ingestion_failures")
    op.drop_table("ingestion_failures")
