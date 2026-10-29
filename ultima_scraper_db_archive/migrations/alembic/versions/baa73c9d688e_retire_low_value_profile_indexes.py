"""Retire low-value profile indexes and index case-insensitive username lookups.

Revision ID: baa73c9d688e
Revises: 88dddeb4538e

Most ``users``/``user_infos`` rows are probed non-performer profiles, so
several full-table indexes cover columns that are constant or almost always
NULL. Each is replaced by a partial index over the rows queries can select,
or dropped when no query can use it:

* ``users``: ``username`` becomes ``lower(username)`` (lookups compare
  ``lower(username)``); ``active`` is always true; ``(active, performer)``
  becomes a performer-only partial index; plain ``last_checked_at`` matches no
  query ordering (the COALESCE index serves the browser sort);
  ``downloaded_at`` keeps only non-NULL rows.
* ``user_infos``: ``user_id`` duplicates ``uq_user_infos_user_id``; ``price``
  keeps paid rows; ``downloaded_at`` and the demographic columns keep non-NULL
  rows; ``verified``/``ai_assisted`` keep true rows.
* ``invalid_users``: ``site`` is constant inside each site schema.
* ``user_aliases`` gains ``lower(username)`` for the same lookups.

Replacements are built before anything is dropped. All DDL runs concurrently
outside the Alembic transaction, so an interrupted upgrade can leave finished
or invalid indexes behind; rerunning rebuilds invalid replacements and skips
finished steps. A name holding an unexpected definition aborts for review.
"""

import re
from typing import NamedTuple, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "baa73c9d688e"
down_revision: Union[str, Sequence[str], None] = "88dddeb4538e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")
DEMOGRAPHIC_COLUMNS = (
    "sex",
    "gender",
    "profile_type",
    "sexual_content",
    "partner_sex",
    "partner_gender",
)
FLAG_COLUMNS = ("verified", "ai_assisted")


class IndexSpec(NamedTuple):
    name: str
    table: str
    # pg_get_indexdef(index, position, true) for each key, in order.
    keys: tuple[str, ...]
    # SQL passed to CREATE INDEX for each key.
    sql: tuple[str, ...]
    predicate: str | None = None
    descending_nulls_last: bool = False


def _plain(name: str, table: str, column: str) -> IndexSpec:
    return IndexSpec(name, table, (column,), (column,))


def _recent(name: str, table: str, column: str, predicate: str | None) -> IndexSpec:
    return IndexSpec(
        name,
        table,
        (column,),
        (f"{column} DESC NULLS LAST",),
        predicate,
        descending_nulls_last=True,
    )


REPLACEMENTS = (
    IndexSpec(
        "idx_users_username_lower", "users", ("lower(username)",), ("lower(username)",)
    ),
    IndexSpec("idx_users_performer", "users", ("id",), ("id",), "performer IS TRUE"),
    _recent(
        "idx_users_downloaded_at_present",
        "users",
        "downloaded_at",
        "downloaded_at IS NOT NULL",
    ),
    IndexSpec(
        "idx_user_infos_price_paid", "user_infos", ("price",), ("price",), "price > 0"
    ),
    _recent(
        "idx_user_infos_downloaded_at_present",
        "user_infos",
        "downloaded_at",
        "downloaded_at IS NOT NULL",
    ),
    *(
        IndexSpec(
            f"idx_user_infos_{column}",
            "user_infos",
            (column,),
            (column,),
            f"{column} IS NOT NULL",
        )
        for column in DEMOGRAPHIC_COLUMNS
    ),
    *(
        IndexSpec(
            f"idx_user_infos_{column}",
            "user_infos",
            ("user_id",),
            ("user_id",),
            f"{column} IS TRUE",
        )
        for column in FLAG_COLUMNS
    ),
    IndexSpec(
        "idx_user_aliases_username_lower",
        "user_aliases",
        ("lower(username)",),
        ("lower(username)",),
    ),
)


def retired_indexes(schema: str) -> tuple[IndexSpec, ...]:
    """Return the full-table indexes this revision removes from ``schema``."""

    return (
        _plain("idx_users_username", "users", "username"),
        _plain("idx_users_active", "users", "active"),
        IndexSpec(
            "idx_users_active_performer",
            "users",
            ("active", "performer"),
            ("active", "performer"),
        ),
        _recent("idx_users_last_checked_at", "users", "last_checked_at", None),
        _recent("idx_users_downloaded_at", "users", "downloaded_at", None),
        _plain("idx_user_infos_user_id", "user_infos", "user_id"),
        _plain("idx_user_infos_price", "user_infos", "price"),
        _recent("idx_user_infos_downloaded_at", "user_infos", "downloaded_at", None),
        *(
            _plain(f"ix_{schema}_user_infos_{column}", "user_infos", column)
            for column in (*DEMOGRAPHIC_COLUMNS, *FLAG_COLUMNS)
        ),
        _plain("idx_invalid_users_site", "invalid_users", "site"),
    )


_INDEX_INFO = sa.text("""
SELECT t.relname AS table_name, am.amname AS method,
       i.indisvalid AS valid, i.indisready AS ready,
       i.indisunique AS unique_index, i.indnkeyatts AS key_count,
       i.indnatts AS column_count,
       pg_get_expr(i.indpred, i.indrelid) AS predicate,
       ARRAY(SELECT pg_get_indexdef(i.indexrelid, position, true)
             FROM generate_series(1, i.indnkeyatts) AS position
             ORDER BY position) AS keys,
       ARRAY(SELECT i.indoption[position - 1]::int
             FROM generate_series(1, i.indnkeyatts) AS position
             ORDER BY position) AS options,
       EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid = c.oid)
           AS constraint_backed
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_am am ON am.oid = c.relam
WHERE n.nspname = :schema AND c.relname = :name
""")

# indoption bit 0 is DESC; bit 1 is NULLS FIRST. DESC NULLS LAST is 1.
_DESC_NULLS_LAST = 1


def _normalize(value: str | None) -> str:
    value = re.sub(r"::(?:double precision|integer|numeric|text)", "", (value or "").lower())
    return re.sub(r"[\s()]", "", value)


def _existing(schema: str, name: str):
    if op.get_context().as_sql:
        return None
    return (
        op.get_bind()
        .execute(_INDEX_INFO, {"schema": schema, "name": name})
        .mappings()
        .one_or_none()
    )


def _matches(existing, spec: IndexSpec) -> bool:
    option = _DESC_NULLS_LAST if spec.descending_nulls_last else 0
    return (
        existing["table_name"] == spec.table
        and existing["method"] == "btree"
        and not existing["unique_index"]
        and not existing["constraint_backed"]
        and existing["key_count"] == len(spec.keys)
        and existing["column_count"] == len(spec.keys)
        and [_normalize(key) for key in existing["keys"]]
        == [_normalize(key) for key in spec.keys]
        and list(existing["options"]) == [option] * len(spec.keys)
        and _normalize(existing["predicate"]) == _normalize(spec.predicate)
    )


def _review(schema: str, name: str) -> RuntimeError:
    return RuntimeError(
        f"Existing index {schema}.{name} has an unexpected definition; "
        "review it before retrying the migration."
    )


def _create(schema: str, spec: IndexSpec) -> None:
    existing = _existing(schema, spec.name)
    if existing is not None:
        if not _matches(existing, spec):
            raise _review(schema, spec.name)
        if existing["valid"] and existing["ready"]:
            return
        # Only replace a failed concurrent build of this exact definition.
        op.drop_index(
            spec.name,
            table_name=spec.table,
            schema=schema,
            postgresql_concurrently=True,
        )
    op.create_index(
        spec.name,
        spec.table,
        [sa.text(sql) for sql in spec.sql],
        schema=schema,
        postgresql_where=sa.text(spec.predicate) if spec.predicate else None,
        postgresql_concurrently=True,
        if_not_exists=op.get_context().as_sql,
    )


def _drop(schema: str, spec: IndexSpec) -> None:
    existing = _existing(schema, spec.name)
    if existing is not None and not _matches(existing, spec):
        raise _review(schema, spec.name)
    if existing is None and not op.get_context().as_sql:
        return
    op.drop_index(
        spec.name,
        table_name=spec.table,
        schema=schema,
        postgresql_concurrently=True,
        if_exists=True,
    )


def upgrade() -> None:
    for schema in SCHEMAS:
        with op.get_context().autocommit_block():
            for spec in REPLACEMENTS:
                _create(schema, spec)
            for spec in retired_indexes(schema):
                _drop(schema, spec)


def downgrade() -> None:
    """Rebuild the full-table indexes; needs time, disk and write I/O."""

    for schema in reversed(SCHEMAS):
        with op.get_context().autocommit_block():
            for spec in retired_indexes(schema):
                _create(schema, spec)
            for spec in reversed(REPLACEMENTS):
                _drop(schema, spec)
