"""Rebuild auth and media_urls with user_id semantics

Revision ID: 9c6b7f4e2a11
Revises: 21a95ba68935, 5d21dc512ae1
Create Date: 2026-02-22 07:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection


# revision identifiers, used by Alembic.
revision: str = "9c6b7f4e2a11"
down_revision: Union[str, Sequence[str], None] = ("21a95ba68935", "5d21dc512ae1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_SUFFIX = "_legacy_20260222"
_LEGACY_USER_AUTHS = f"user_auths{_LEGACY_SUFFIX}"
_LEGACY_MEDIA_URLS = f"media_urls{_LEGACY_SUFFIX}"


def _q(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _table_exists(conn: Connection, schema: str, table: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema AND table_name = :table
            )
            """
        ),
        {"schema": schema, "table": table},
    )
    return bool(result.scalar())


def _legacy_name(name: str) -> str:
    # PostgreSQL identifier limit is 63 bytes/chars.
    max_len = 63
    if len(name) + len(_LEGACY_SUFFIX) <= max_len:
        return f"{name}{_LEGACY_SUFFIX}"
    return f"{name[: max_len - len(_LEGACY_SUFFIX)]}{_LEGACY_SUFFIX}"


def _rename_legacy_objects(conn: Connection, schema: str, table: str) -> None:
    # Rename constraints first (pkey/unique/fk names).
    constraints = conn.execute(
        text(
            """
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = :schema AND t.relname = :table
            """
        ),
        {"schema": schema, "table": table},
    ).fetchall()
    for (constraint_name,) in constraints:
        new_name = _legacy_name(constraint_name)
        if new_name == constraint_name:
            continue
        try:
            conn.exec_driver_sql(
                f"ALTER TABLE {_q(schema)}.{_q(table)} "
                f"RENAME CONSTRAINT {_q(constraint_name)} TO {_q(new_name)}"
            )
        except Exception:
            # Best-effort: avoid failing migration on legacy name collisions.
            pass

    # Rename indexes so canonical names are available for new tables.
    indexes = conn.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = :schema AND tablename = :table
            """
        ),
        {"schema": schema, "table": table},
    ).fetchall()
    for (index_name,) in indexes:
        new_name = _legacy_name(index_name)
        if new_name == index_name:
            continue
        try:
            conn.exec_driver_sql(
                f"ALTER INDEX {_q(schema)}.{_q(index_name)} "
                f"RENAME TO {_q(new_name)}"
            )
        except Exception:
            # Best-effort: avoid failing migration on legacy name collisions.
            pass


def _discover_site_schemas(conn: Connection) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT table_schema
            FROM information_schema.tables
            WHERE table_name IN ('user_auths', 'media_urls')
              AND table_schema NOT IN (
                  'pg_catalog', 'information_schema', 'pg_toast', 'public', 'management'
              )
            ORDER BY table_schema
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _create_user_auths(schema: str) -> None:
    op.create_table(
        "user_auths",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site", sa.String(length=64), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("cookie", sa.Text(), nullable=True),
        sa.Column("x_bc", sa.Text(), nullable=True),
        sa.Column("authorization", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("proxy_id", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("last_tested_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_age_verified", sa.Boolean(), nullable=True),
        sa.Column("age_verification_required", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{schema}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cookie", "authorization", name="uq_user_auths_cookie_auth"),
        schema=schema,
    )
    op.create_index("idx_user_auths_site", "user_auths", ["site"], unique=False, schema=schema)
    op.create_index("idx_user_auths_user_id", "user_auths", ["user_id"], unique=False, schema=schema)
    op.create_index("idx_user_auths_username", "user_auths", ["username"], unique=False, schema=schema)
    op.create_index(f"ix_{schema}_user_auths_site", "user_auths", ["site"], unique=False, schema=schema)
    op.create_index(
        f"ix_{schema}_user_auths_username", "user_auths", ["username"], unique=False, schema=schema
    )


def _create_media_urls(schema: str) -> None:
    op.create_table(
        "media_urls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("media_id", sa.BigInteger(), nullable=False),
        # Store platform account user id (users.id), not user_auths.id.
        sa.Column("auth_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], [f"{schema}.media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["auth_id"], [f"{schema}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_id", "auth_id", name="uq_media_urls_media_auth"),
        schema=schema,
    )
    op.create_index("idx_media_urls_auth_id", "media_urls", ["auth_id"], unique=False, schema=schema)
    op.create_index("idx_media_urls_expires_at", "media_urls", ["expires_at"], unique=False, schema=schema)
    op.create_index("idx_media_urls_media_id", "media_urls", ["media_id"], unique=False, schema=schema)
    op.create_index(f"ix_{schema}_media_urls_auth_id", "media_urls", ["auth_id"], unique=False, schema=schema)
    op.create_index(f"ix_{schema}_media_urls_media_id", "media_urls", ["media_id"], unique=False, schema=schema)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    schemas = _discover_site_schemas(conn)

    for schema in schemas:
        # 1) Rename current tables to legacy copies (non-destructive).
        if _table_exists(conn, schema, "user_auths") and not _table_exists(conn, schema, _LEGACY_USER_AUTHS):
            op.rename_table("user_auths", _LEGACY_USER_AUTHS, schema=schema)
            _rename_legacy_objects(conn, schema, _LEGACY_USER_AUTHS)
        if _table_exists(conn, schema, "media_urls") and not _table_exists(conn, schema, _LEGACY_MEDIA_URLS):
            op.rename_table("media_urls", _LEGACY_MEDIA_URLS, schema=schema)
            _rename_legacy_objects(conn, schema, _LEGACY_MEDIA_URLS)

        # 2) Create fresh canonical tables.
        if not _table_exists(conn, schema, "user_auths"):
            _create_user_auths(schema)
        if not _table_exists(conn, schema, "media_urls"):
            _create_media_urls(schema)

        # 3) Backfill user_auths (new IDs start from 1 by autoincrement).
        if _table_exists(conn, schema, _LEGACY_USER_AUTHS):
            conn.exec_driver_sql(
                f"""
                INSERT INTO {_q(schema)}.user_auths (
                    site, username, user_id, cookie, x_bc, "authorization",
                    user_agent, email, password, proxy_id, status, last_tested_at,
                    active, is_age_verified, age_verification_required,
                    created_at, updated_at
                )
                SELECT
                    site,
                    username,
                    user_id,
                    cookie,
                    x_bc,
                    "authorization",
                    user_agent,
                    email,
                    password,
                    proxy_id,
                    COALESCE(status, 'unknown'),
                    last_tested_at,
                    COALESCE(active, true),
                    is_age_verified,
                    age_verification_required,
                    COALESCE(created_at, now()),
                    updated_at
                FROM {_q(schema)}.{_q(_LEGACY_USER_AUTHS)}
                ORDER BY id
                ON CONFLICT ON CONSTRAINT uq_user_auths_cookie_auth DO NOTHING
                """
            )

        # 4) Backfill media_urls with users.id semantics.
        if _table_exists(conn, schema, _LEGACY_MEDIA_URLS):
            if _table_exists(conn, schema, _LEGACY_USER_AUTHS):
                conn.exec_driver_sql(
                    f"""
                    INSERT INTO {_q(schema)}.media_urls (
                        media_id, auth_id, url, expires_at, created_at, updated_at
                    )
                    SELECT
                        ml.media_id,
                        COALESCE(ua.user_id, ml.auth_id) AS resolved_auth_user_id,
                        ml.url,
                        ml.expires_at,
                        COALESCE(ml.created_at, now()),
                        COALESCE(ml.updated_at, now())
                    FROM {_q(schema)}.{_q(_LEGACY_MEDIA_URLS)} AS ml
                    LEFT JOIN {_q(schema)}.{_q(_LEGACY_USER_AUTHS)} AS ua
                        ON ua.id = ml.auth_id
                    JOIN {_q(schema)}.media AS m
                        ON m.id = ml.media_id
                    JOIN {_q(schema)}.users AS u
                        ON u.id = COALESCE(ua.user_id, ml.auth_id)
                    WHERE ml.media_id IS NOT NULL
                    ON CONFLICT ON CONSTRAINT uq_media_urls_media_auth DO UPDATE
                    SET
                        url = EXCLUDED.url,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = EXCLUDED.updated_at
                    """
                )
            else:
                conn.exec_driver_sql(
                    f"""
                    INSERT INTO {_q(schema)}.media_urls (
                        media_id, auth_id, url, expires_at, created_at, updated_at
                    )
                    SELECT
                        ml.media_id,
                        ml.auth_id,
                        ml.url,
                        ml.expires_at,
                        COALESCE(ml.created_at, now()),
                        COALESCE(ml.updated_at, now())
                    FROM {_q(schema)}.{_q(_LEGACY_MEDIA_URLS)} AS ml
                    JOIN {_q(schema)}.media AS m
                        ON m.id = ml.media_id
                    JOIN {_q(schema)}.users AS u
                        ON u.id = ml.auth_id
                    WHERE ml.media_id IS NOT NULL
                    ON CONFLICT ON CONSTRAINT uq_media_urls_media_auth DO UPDATE
                    SET
                        url = EXCLUDED.url,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = EXCLUDED.updated_at
                    """
                )


def downgrade() -> None:
    """Downgrade is intentionally non-destructive and unsupported."""
    raise RuntimeError(
        "Downgrade not supported for 9c6b7f4e2a11; "
        "legacy tables were preserved with *_legacy_20260222 names."
    )
