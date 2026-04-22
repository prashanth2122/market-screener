"""baseline migration framework

Revision ID: 20260422_01
Revises:
Create Date: 2026-04-22 22:00:00
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20260422_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Initialize Alembic versioning baseline."""

    pass


def downgrade() -> None:
    """No-op baseline downgrade."""

    pass
