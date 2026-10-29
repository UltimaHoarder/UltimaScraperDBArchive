"""Align settings.updated_at and websites.id with their models.

The initial migration created management.settings.updated_at nullable with no
default, while ``SettingsModel`` declares ``server_default=now()`` and
``nullable=False``. Rows inserted without the column therefore stored NULL, and
every database built from migrations reported this column as schema drift.

Migration f2c4e8a1b9d7 creates ``websites.id`` as BIGSERIAL, but only with
CREATE TABLE IF NOT EXISTS: a site schema whose table already existed kept a
32-bit id. Widen any such column so every site matches ``WebsiteModel``.

Revision ID: c3e9f17a5d48
Revises: b7c41e9a2d58
Create Date: 2026-10-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9f17a5d48"
down_revision: Union[str, Sequence[str], None] = "b7c41e9a2d58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Backfill NULL timestamps, add the default and NOT NULL, widen websites.id."""
    for schema in SITE_SCHEMAS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = 'websites'
                      AND column_name = 'id' AND data_type = 'integer'
                ) THEN
                    ALTER TABLE {schema}.websites ALTER COLUMN id TYPE BIGINT;
                END IF;
            END $$;
            """
        )
    op.execute(
        "UPDATE management.settings "
        "SET updated_at = coalesce(created_at, now()) WHERE updated_at IS NULL"
    )
    op.alter_column(
        "settings",
        "updated_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
        schema="management",
    )


def downgrade() -> None:
    """Restore the original nullable settings column; websites.id stays BIGINT."""
    op.alter_column(
        "settings",
        "updated_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        server_default=None,
        nullable=True,
        schema="management",
    )
