"""Merge bought-content uniqueness and query-perf branches

Revision ID: d693ae680246
Revises: a7c3d1e5f290, c4a5f16d7e2b
Create Date: 2026-03-12 18:10:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "d693ae680246"
down_revision: Union[str, Sequence[str], None] = (
    "a7c3d1e5f290",
    "c4a5f16d7e2b",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge branches with no additional schema changes."""


def downgrade() -> None:
    """Unmerge branches with no additional schema changes."""
