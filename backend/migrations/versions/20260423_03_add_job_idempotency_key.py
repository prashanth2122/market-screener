"""add idempotency key to jobs

Revision ID: 20260423_03
Revises: 20260422_02
Create Date: 2026-04-23 01:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260423_03"
down_revision: Union[str, None] = "20260422_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add job-level idempotency key for repeated pull checks."""

    op.add_column("jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index(
        "ix_jobs_name_idempotency",
        "jobs",
        ["job_name", "idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    """Remove job-level idempotency key."""

    op.drop_index("ix_jobs_name_idempotency", table_name="jobs")
    op.drop_column("jobs", "idempotency_key")
