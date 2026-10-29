"""Add search loadouts and repair database-owned runtime sequences.

Revision ID: 7a2d9c4e1f80
Revises: f6a1c8e29b47
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a2d9c4e1f80"
down_revision: str | Sequence[str] | None = "f6a1c8e29b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SITE_SCHEMAS = ("onlyfans", "fansly", "loyalfans")
RUNTIME_SEQUENCE_TABLES = ("content_media_asso", "filepaths")


def upgrade() -> None:
    """Move runtime-owned schema work into the owner-run migration graph."""
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS management.search_loadouts (
                id bigserial PRIMARY KEY,
                loadout_type varchar(32) NOT NULL,
                name varchar(90) NOT NULL,
                identifier text NOT NULL DEFAULT '',
                description text NOT NULL DEFAULT '',
                site varchar(32) NOT NULL DEFAULT '',
                filters_json text NOT NULL DEFAULT '{}',
                is_default boolean NOT NULL DEFAULT false,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT uq_search_loadouts_type_name
                    UNIQUE (loadout_type, name)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'management.search_loadouts'::regclass
                      AND conname = 'uq_search_loadouts_type_name'
                ) THEN
                    ALTER TABLE management.search_loadouts
                    ADD CONSTRAINT uq_search_loadouts_type_name
                    UNIQUE (loadout_type, name);
                END IF;
            END
            $$
            """
        )
    )
    op.create_index(
        "idx_search_loadouts_type",
        "search_loadouts",
        ["loadout_type"],
        schema="management",
        if_not_exists=True,
    )
    op.create_index(
        "idx_search_loadouts_is_default",
        "search_loadouts",
        ["is_default"],
        schema="management",
        if_not_exists=True,
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION management.touch_search_loadouts_row()
            RETURNS trigger AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_search_loadouts_touch_update
            ON management.search_loadouts
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_search_loadouts_touch_update
            BEFORE UPDATE ON management.search_loadouts
            FOR EACH ROW
            EXECUTE FUNCTION management.touch_search_loadouts_row()
            """
        )
    )

    # Older imports could leave these database-generated ids ahead of their
    # backing sequences. Repair them once as the migration owner; runtimes do
    # not need UPDATE on sequences merely to insert ordinary rows.
    for schema in SITE_SCHEMAS:
        for table in RUNTIME_SEQUENCE_TABLES:
            op.execute(
                sa.text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{schema}.{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {schema}.{table}), 0) + 1,
                        false
                    )
                    """
                )
            )


def downgrade() -> None:
    """Remove search loadout persistence without rewinding repaired sequences."""
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_search_loadouts_touch_update
            ON management.search_loadouts
            """
        )
    )
    op.execute(
        sa.text(
            """
            DROP FUNCTION IF EXISTS management.touch_search_loadouts_row()
            """
        )
    )
    op.drop_table("search_loadouts", schema="management")
