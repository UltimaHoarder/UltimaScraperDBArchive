"""Add active user and content type breakdown fields to daily statistics snapshots.

Revision ID: a4b8e19f23c0
Revises: d5e1a7c39b42
Create Date: 2026-10-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b8e19f23c0"
down_revision: Union[str, Sequence[str], None] = "d5e1a7c39b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")
NEW_COLUMNS: tuple[str, ...] = (
    "active_user_count",
    "post_count",
    "message_count",
    "story_count",
    "mass_message_count",
)


def upgrade() -> None:
    """Add nullable user status and content breakdown columns."""
    for schema in SITE_SCHEMAS:
        for column_name in NEW_COLUMNS:
            op.add_column(
                "statistics",
                sa.Column(column_name, sa.BigInteger(), nullable=True),
                schema=schema,
            )


def downgrade() -> None:
    """Remove the user status and content breakdown columns."""
    for schema in SITE_SCHEMAS:
        for column_name in reversed(NEW_COLUMNS):
            op.drop_column("statistics", column_name, schema=schema)
