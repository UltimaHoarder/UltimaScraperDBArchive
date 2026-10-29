"""Promote the user sorting indexes to every site schema.

Revision ID: f6a1c8e29b47
Revises: d8f4c2a9e631
Create Date: 2026-08-22 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a1c8e29b47"
down_revision: str | Sequence[str] | None = "d8f4c2a9e631"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")
INDEXES = (
    (
        "idx_onlyfans_users_created_at",
        "idx_users_created_at",
        "users",
        "created_at DESC NULLS LAST",
    ),
    (
        "idx_onlyfans_users_downloaded_at",
        "idx_users_downloaded_at",
        "users",
        "downloaded_at DESC NULLS LAST",
    ),
    (
        "idx_onlyfans_users_last_checked_at",
        "idx_users_last_checked_at",
        "users",
        "last_checked_at DESC NULLS LAST",
    ),
    (
        "idx_onlyfans_users_last_checked_coalesce",
        "idx_users_last_checked_coalesce",
        "users",
        "COALESCE(last_checked_at, updated_at) DESC NULLS LAST",
    ),
    (
        "idx_onlyfans_user_infos_downloaded_at",
        "idx_user_infos_downloaded_at",
        "user_infos",
        "downloaded_at DESC NULLS LAST",
    ),
    (
        "idx_onlyfans_user_infos_media_count",
        "idx_user_infos_media_count",
        "user_infos",
        "media_count DESC NULLS LAST",
    ),
)


def upgrade() -> None:
    """Reuse the OnlyFans indexes and create equivalents for every site."""
    for old_name, name, _table, _expression in INDEXES:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('onlyfans.{name}') IS NULL
                       AND to_regclass('onlyfans.{old_name}') IS NOT NULL THEN
                        ALTER INDEX onlyfans.{old_name} RENAME TO {name};
                    END IF;
                END
                $$
                """
            )
        )

    for schema in SCHEMAS:
        for _old_name, name, table, expression in INDEXES:
            with op.get_context().autocommit_block():
                op.create_index(
                    name,
                    table,
                    [sa.text(expression)],
                    unique=False,
                    schema=schema,
                    postgresql_concurrently=True,
                    if_not_exists=True,
                )


def downgrade() -> None:
    """Remove added site indexes and restore the original OnlyFans names."""
    for schema in reversed(SCHEMAS[1:]):
        for _old_name, name, table, _expression in reversed(INDEXES):
            with op.get_context().autocommit_block():
                op.drop_index(
                    name,
                    table_name=table,
                    schema=schema,
                    postgresql_concurrently=True,
                    if_exists=True,
                )

    for old_name, name, _table, _expression in reversed(INDEXES):
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('onlyfans.{old_name}') IS NULL
                       AND to_regclass('onlyfans.{name}') IS NOT NULL THEN
                        ALTER INDEX onlyfans.{name} RENAME TO {old_name};
                    END IF;
                END
                $$
                """
            )
        )
