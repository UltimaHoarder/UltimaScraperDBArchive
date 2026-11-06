"""Add management.cluster.secret_key_check, so every backend uses one key.

Backends that share a database read each other's encrypted secrets, so they
need the same USR_SECRET_KEY. The column holds a fixed value encrypted with
that key; a backend whose key can't decrypt it refuses to start.

Revision ID: e8a3f5c2b694
Revises: d2e9b4c7a1f3
Create Date: 2026-11-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8a3f5c2b694"
down_revision: Union[str, Sequence[str], None] = "d2e9b4c7a1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the empty check; the first backend to start fills it in."""
    op.add_column(
        "cluster",
        sa.Column("secret_key_check", sa.Text(), nullable=True),
        schema="management",
    )


def downgrade() -> None:
    """Drop the check; backends then no longer compare keys."""
    op.drop_column("cluster", "secret_key_check", schema="management")
