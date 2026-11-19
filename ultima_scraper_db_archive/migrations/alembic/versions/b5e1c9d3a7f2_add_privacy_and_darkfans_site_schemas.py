"""Add the Privacy and DarkFans site schemas.

A site's archive lives in a schema named after it, with the same tables as
every other site. Earlier revisions built the three original schemas one change
at a time, so the new ones are copied from ``loyalfans`` as it stands at this
revision: its tables (columns, defaults, storage), constraints, indexes and
grants, with each serial column given a sequence of its own and every name
that mentions ``loyalfans`` renamed for the new site. The favourites table
gets the same per-site partitions the original sites have, and since a new
site has no legacy favourites to copy it starts out cut over (as
``favourites_migration activate-empty`` would mark it).

An installation may already have created the new schemas empty before running
migrations; a schema that already has tables is left alone.

Revision ID: b5e1c9d3a7f2
Revises: f3b7d2a84c16
Create Date: 2026-11-18 00:00:00.000000

"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

revision: str = "b5e1c9d3a7f2"
down_revision: Union[str, Sequence[str], None] = "f3b7d2a84c16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE = "loyalfans"
NEW_SITES = ("privacy", "darkfans")
# Favourite kind -> the site table its rows point at (see ce84a19f027b).
FAVOURITE_TARGETS = {"user": "users", "post": "x_posts", "story": "x_stories", "message": "x_messages"}

# "loyalfans" as a whole word, where "_" also separates words.
_TEMPLATE_WORD = re.compile(rf"(?<![A-Za-z0-9]){TEMPLATE}(?![A-Za-z0-9])")


def _for_site(sql: str, site: str) -> str:
    """``sql`` with every schema qualifier and name part naming the template
    renamed for ``site`` (definitions here hold no site-name literals)."""
    return _TEMPLATE_WORD.sub(site, sql)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _has_tables(conn: Connection, schema: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = :schema AND c.relkind IN ('r', 'p'))"
            ),
            {"schema": schema},
        ).scalar()
    )


def _template_tables(conn: Connection) -> list[str]:
    return list(
        conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = :schema AND c.relkind = 'r' AND NOT c.relispartition"
                " ORDER BY c.relname"
            ),
            {"schema": TEMPLATE},
        ).scalars()
    )


def _copy_grants(conn: Connection, site: str) -> None:
    """Grant on the new schema, tables and sequences what the template's
    owner granted on its own, to the same roles."""
    rows = conn.execute(
        text(
            """
            SELECT 'SCHEMA' AS kind, NULL AS name, a.privilege_type, a.grantee
              FROM pg_namespace n, aclexplode(n.nspacl) a
             WHERE n.nspname = :schema AND a.grantee <> n.nspowner
            UNION ALL
            SELECT CASE c.relkind WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END,
                   c.relname, a.privilege_type, a.grantee
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
                   aclexplode(c.relacl) a
             WHERE n.nspname = :schema AND c.relkind IN ('r', 'S')
               AND NOT c.relispartition AND a.grantee <> c.relowner
            """
        ),
        {"schema": TEMPLATE},
    ).all()
    for kind, name, privilege, grantee_oid in rows:
        grantee = (
            "PUBLIC"
            if grantee_oid == 0
            else _quote(conn.execute(text("SELECT rolname FROM pg_roles WHERE oid = :oid"), {"oid": grantee_oid}).scalar_one())
        )
        target = _quote(site) if kind == "SCHEMA" else f"{_quote(site)}.{_quote(_for_site(name, site))}"
        conn.execute(text(f"GRANT {privilege} ON {kind} {target} TO {grantee}"))


def _clone_schema(conn: Connection, site: str) -> None:
    tables = _template_tables(conn)
    for table in tables:
        conn.execute(
            text(
                f"CREATE TABLE {_quote(site)}.{_quote(table)} (LIKE {TEMPLATE}.{_quote(table)}"
                " INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY INCLUDING STORAGE"
                " INCLUDING COMMENTS INCLUDING COMPRESSION)"
            )
        )

    # Serial columns: LIKE copied defaults that still draw from the template's
    # sequences; give each its own (same name, type and owner column).
    serials = conn.execute(
        text(
            """
            SELECT t.relname, a.attname, s.relname, format_type(q.seqtypid, NULL)
              FROM pg_depend d
              JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
              JOIN pg_sequence q ON q.seqrelid = s.oid
              JOIN pg_class t ON t.oid = d.refobjid
              JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = :schema AND d.deptype = 'a' AND d.classid = 'pg_class'::regclass
             ORDER BY t.relname, a.attname
            """
        ),
        {"schema": TEMPLATE},
    ).all()
    for table, column, sequence, data_type in serials:
        new_sequence = f"{_quote(site)}.{_quote(_for_site(sequence, site))}"
        conn.execute(text(f"CREATE SEQUENCE {new_sequence} AS {data_type}"))
        conn.execute(text(f"ALTER SEQUENCE {new_sequence} OWNED BY {_quote(site)}.{_quote(table)}.{_quote(column)}"))
        conn.execute(
            text(
                f"ALTER TABLE {_quote(site)}.{_quote(table)} ALTER COLUMN {_quote(column)}"
                f" SET DEFAULT nextval('{new_sequence}'::regclass)"
            )
        )

    # Constraints keep their names; foreign keys go last, once every table
    # they may point at has its keys. Not-null constraints came with LIKE.
    constraints = conn.execute(
        text(
            """
            SELECT t.relname, c.conname, pg_get_constraintdef(c.oid), c.contype
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = :schema AND c.contype IN ('p', 'u', 'c', 'x', 'f')
               AND NOT t.relispartition
             ORDER BY c.contype = 'f', t.relname, c.conname
            """
        ),
        {"schema": TEMPLATE},
    ).all()
    for table, name, definition, _kind in constraints:
        conn.execute(
            text(
                f"ALTER TABLE {_quote(site)}.{_quote(table)} ADD CONSTRAINT"
                f" {_quote(_for_site(name, site))} {_for_site(definition, site)}"
            )
        )

    # The remaining indexes, by their own definitions (names included).
    indexes = conn.execute(
        text(
            """
            SELECT pg_get_indexdef(i.indexrelid)
              FROM pg_index i
              JOIN pg_class t ON t.oid = i.indrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = :schema AND t.relkind = 'r' AND NOT t.relispartition
               AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
             ORDER BY 1
            """
        ),
        {"schema": TEMPLATE},
    ).scalars()
    for definition in list(indexes):
        conn.execute(text(_for_site(definition, site)))

    _copy_grants(conn, site)


def _add_favourites(conn: Connection, site: str) -> None:
    if conn.execute(text("SELECT to_regclass('management.favourites')")).scalar() is None:
        return
    parent = f"management.favourites_{site}"
    if conn.execute(text("SELECT to_regclass(:name)"), {"name": parent}).scalar() is None:
        conn.execute(
            text(
                f"CREATE TABLE {parent} PARTITION OF management.favourites"
                f" FOR VALUES IN ('{site}') PARTITION BY LIST (entity_type)"
            )
        )
        for kind, table in FAVOURITE_TARGETS.items():
            name = f"favourites_{site}_{kind}"
            conn.execute(
                text(
                    f"CREATE TABLE management.{name} PARTITION OF {parent} FOR VALUES IN ('{kind}')"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE management.{name} ADD CONSTRAINT fk_{name}_target"
                    f" FOREIGN KEY (entity_id) REFERENCES {site}.{table}(id) ON DELETE CASCADE"
                )
            )
    if conn.execute(text("SELECT to_regclass('management.favourites_migration')")).scalar() is not None:
        conn.execute(
            text(
                "INSERT INTO management.favourites_migration (site, complete, validated, active)"
                " VALUES (:site, true, true, true) ON CONFLICT (site) DO NOTHING"
            ),
            {"site": site},
        )


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    # Fully qualified definitions, so renaming the schema is a text change.
    conn.execute(text("SET LOCAL search_path TO pg_catalog"))
    for site in NEW_SITES:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_quote(site)}"))
        if not _has_tables(conn, site):
            _clone_schema(conn, site)
        _add_favourites(conn, site)
    conn.execute(text("SET LOCAL search_path TO public"))


def downgrade() -> None:
    """Drop the new schemas; refused once either holds any user."""
    conn = op.get_bind()
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    for site in NEW_SITES:
        users = conn.execute(text("SELECT to_regclass(:name)"), {"name": f"{site}.users"}).scalar()
        if users is not None and conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {site}.users)")).scalar():
            raise RuntimeError(f"{site} holds archived users; drop its schema by hand if that is intended")
    for site in NEW_SITES:
        conn.execute(text("DELETE FROM management.favourites_migration WHERE site = :site"), {"site": site})
        conn.execute(text(f"DROP TABLE IF EXISTS management.favourites_{site}"))
        conn.execute(text(f"DROP SCHEMA IF EXISTS {_quote(site)} CASCADE"))
