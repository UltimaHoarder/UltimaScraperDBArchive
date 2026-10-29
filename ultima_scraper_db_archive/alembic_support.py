"""Helpers that keep Alembic reflection deterministic through PgBouncer."""

from __future__ import annotations

from sqlalchemy.engine import Connection


def normalize_postgresql_reflection(connection: Connection) -> None:
    """Normalize PostgreSQL reflection inside Alembic's active transaction."""

    if connection.dialect.name != "postgresql":
        return
    if not connection.in_transaction():
        raise RuntimeError(
            "PostgreSQL reflection must be normalized inside Alembic's transaction"
        )

    connection.exec_driver_sql("SET LOCAL search_path TO public")
    connection.dialect.default_schema_name = "public"
