"""add dead letter payloads table

Revision ID: 20260428_10
Revises: 20260424_09
Create Date: 2026-04-28 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260428_10"
down_revision: Union[str, None] = "20260424_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dead-letter queue table for non-retryable ingestion payload failures."""

    op.create_table(
        "dead_letter_payloads",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("dead_letter_key", sa.String(length=160), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("asset_symbol", sa.String(length=32), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("payload_type", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("dead_letter_key", name="uq_dead_letter_payloads_dead_letter_key"),
    )
    op.create_index(
        "ix_dead_letter_payloads_job_symbol",
        "dead_letter_payloads",
        ["job_name", "asset_symbol"],
        unique=False,
    )
    op.create_index(
        "ix_dead_letter_payloads_last_seen",
        "dead_letter_payloads",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_dead_letter_payloads_provider_type",
        "dead_letter_payloads",
        ["provider_name", "payload_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop dead-letter queue table."""

    op.drop_index("ix_dead_letter_payloads_provider_type", table_name="dead_letter_payloads")
    op.drop_index("ix_dead_letter_payloads_last_seen", table_name="dead_letter_payloads")
    op.drop_index("ix_dead_letter_payloads_job_symbol", table_name="dead_letter_payloads")
    op.drop_table("dead_letter_payloads")
