"""Add archive inventory fields to daily statistics snapshots.

Revision ID: d2c4f71a6b90
Revises: ba4ce359afb9
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2c4f71a6b90"
down_revision: Union[str, Sequence[str], None] = "ba4ce359afb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Add nullable counts; existing daily rows have no historical backfill."""
    for schema in SITE_SCHEMAS:
        for column_name in (
            "user_record_count",
            "performer_profile_count",
            "archived_content_count",
            "downloaded_media_count",
        ):
            op.add_column(
                "statistics",
                sa.Column(column_name, sa.BigInteger(), nullable=True),
                schema=schema,
            )


def downgrade() -> None:
    """Remove the inventory fields from each site statistics table."""
    for schema in SITE_SCHEMAS:
        for column_name in (
            "downloaded_media_count",
            "archived_content_count",
            "performer_profile_count",
            "user_record_count",
        ):
            op.drop_column("statistics", column_name, schema=schema)
