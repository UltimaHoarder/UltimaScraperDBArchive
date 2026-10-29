"""Cover active performer and paid-video profile filters.

Revision ID: e9a62c7138bf
Revises: d1e30a7b9462
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "e9a62c7138bf"
down_revision = "d1e30a7b9462"
branch_labels = None
depends_on = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def _normalize_predicate(value: str) -> str:
    value = re.sub(r"::(?:double precision|integer|numeric)", "", value.lower())
    return re.sub(r"[\s()]", "", value)


def _ensure_index(
    schema: str,
    name: str,
    table: str,
    columns: list[str],
    include: list[str],
    predicate: str,
) -> None:
    # Concurrent DDL commits independently of the Alembic revision. A failed
    # upgrade can therefore leave completed or invalid indexes behind.
    if not op.get_context().as_sql:
        existing = (
            op.get_bind()
            .execute(
                sa.text("""
                SELECT t.relname AS table_name, am.amname AS method,
                       i.indisvalid AS valid, i.indisready AS ready,
                       i.indisunique AS unique_index, i.indnkeyatts AS key_count,
                       pg_get_expr(i.indpred, i.indrelid) AS predicate,
                       ARRAY(SELECT pg_get_indexdef(i.indexrelid, position, true)
                             FROM generate_series(1, i.indnatts) AS position
                             ORDER BY position) AS columns
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_index i ON i.indexrelid = c.oid
                JOIN pg_class t ON t.oid = i.indrelid
                JOIN pg_am am ON am.oid = c.relam
                WHERE n.nspname = :schema AND c.relname = :name
            """),
                {"schema": schema, "name": name},
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            matches = (
                existing["table_name"] == table
                and existing["method"] == "btree"
                and not existing["unique_index"]
                and existing["key_count"] == len(columns)
                and list(existing["columns"]) == columns + include
                and _normalize_predicate(existing["predicate"] or "")
                == _normalize_predicate(predicate)
            )
            if not matches:
                raise RuntimeError(
                    f"Existing index {schema}.{name} has an unexpected definition; "
                    "review it before retrying the migration."
                )
            if existing["valid"] and existing["ready"]:
                return
            # Only replace a failed build whose definition matches this revision.
            op.drop_index(
                name, table_name=table, schema=schema, postgresql_concurrently=True
            )

    op.create_index(
        name,
        table,
        columns,
        schema=schema,
        postgresql_include=include,
        postgresql_where=sa.text(predicate),
        postgresql_concurrently=True,
        if_not_exists=op.get_context().as_sql,
    )


def upgrade() -> None:
    for schema in SCHEMAS:
        with op.get_context().autocommit_block():
            _ensure_index(
                schema,
                "idx_users_active_performer_cover",
                "users",
                ["id"],
                ["active", "created_at"],
                "active IS TRUE AND performer IS TRUE",
            )
            _ensure_index(
                schema,
                "idx_user_infos_paid_video_cover",
                "user_infos",
                ["price", "user_id"],
                ["video_count", "sex", "partner_sex"],
                "price > 0 AND video_count > 0",
            )


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        with op.get_context().autocommit_block():
            op.drop_index(
                "idx_user_infos_paid_video_cover",
                table_name="user_infos",
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
            op.drop_index(
                "idx_users_active_performer_cover",
                table_name="users",
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
