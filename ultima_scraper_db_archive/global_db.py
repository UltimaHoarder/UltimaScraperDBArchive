"""Global (cross-site) database access layer.

All management models now live in PostgreSQL under the ``management``
schema of the ``ultima_archive`` database.  This module provides the
session factory (``global_session()``) and re-exports the models so
existing consumers don't need import changes.

Bootstrap order
~~~~~~~~~~~~~~~
1. App starts → reads ``.env`` for ``ULTIMA_ARCHIVE_DATABASE_URL``.
2. If present, ``bootstrap_from_env()`` creates the postgres engine.
3. From that point on every ``global_session()`` call returns a
   postgres-backed ``Session``.

If no ``.env`` exists (first run before setup), global access now fails fast.
SQLite fallback support has been removed so PostgreSQL is the sole source of
truth.
After the first-time setup wizard completes, ``update_env()`` persists
the connection string so subsequent restarts bootstrap automatically.
Setup is complete once this backend's ``management.settings`` config row
exists; see :func:`is_setup_complete`.
"""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy import Engine, event, exc, text
from sqlalchemy.pool import NullPool, QueuePool
from sqlmodel import Session, create_engine
from ultima_scraper_core import (
    archive_database_url,
    get_env_path,
    read_env,
    runtime_env_value,
    write_env,
)

# -------------------------------------------------------------------- #
# Re-export management models from postgres_site so existing imports
# like ``from ultima_scraper_db_archive.global_db import SettingsModel``
# keep working.
# -------------------------------------------------------------------- #
from ultima_scraper_db_archive.databases.ultima_archive.schemas.templates.postgres_site import (  # noqa: F401
    BackendInventoryModel,
    CentralJobModel,
    CentralTaskModel,
    MPSCandidateRangeModel,
    MPSPlanModel,
    MPSTaskDefinitionModel,
    MPSRetryTaskModel,
    DatabaseWriteReceiptModel,
    TaskMediaPlanModel,
    TaskMediaSelectionModel,
    TaskMediaEvidenceModel,
    ProxyGeolocationModel,
    SearchLoadoutModel,
    SettingsModel,
)

__all__ = [
    "BackendInventoryModel",
    "CentralJobModel",
    "CentralTaskModel",
    "MPSCandidateRangeModel",
    "MPSPlanModel",
    "MPSTaskDefinitionModel",
    "MPSRetryTaskModel",
    "DatabaseWriteReceiptModel",
    "TaskMediaPlanModel",
    "TaskMediaSelectionModel",
    "TaskMediaEvidenceModel",
    "ProxyGeolocationModel",
    "SearchLoadoutModel",
    "SettingsModel",
    "bootstrap_from_env",
    "get_env_path",
    "get_global_engine",
    "get_global_session",
    "get_postgres_engine",
    "global_session",
    "is_setup_complete",
    "read_env",
    "set_postgres_engine",
    "set_postgres_url",
    "write_env",
]

_logger = logging.getLogger(__name__)


_SETUP_COMPLETE_SQL = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM management.settings s
        WHERE s.key = 'config'
          AND (
            s.id = (
                SELECT b.settings_id FROM management.backends b
                WHERE b.hostname = :backend
            )
            OR (
                NOT EXISTS (
                    SELECT 1 FROM management.backends b WHERE b.hostname = :backend
                )
                AND s.backend = :backend
            )
          )
    )
    """
)
_setup_complete = False


def is_setup_complete() -> bool:
    """Return whether this backend has a canonical application config row.

    The row written by setup (or the configuration migration) is the only
    setup state. A missing or unreachable database reports ``False``. Positive
    results are cached because the application never deletes that row.
    """
    global _setup_complete
    if _setup_complete:
        return True
    if not archive_database_url():
        return False
    backend_id = runtime_env_value("BACKEND_ID") or socket.gethostname()
    try:
        with Session(get_global_engine()) as session:
            found = session.execute(
                _SETUP_COMPLETE_SQL, {"backend": backend_id}
            ).scalar()
    except Exception:
        _logger.debug("Could not read setup state from PostgreSQL", exc_info=True)
        return False
    _setup_complete = bool(found)
    return _setup_complete


# -------------------------------------------------------------------- #
# Engine management
# -------------------------------------------------------------------- #

def is_sqlite_fallback_allowed() -> bool:
    """SQLite fallback has been removed."""
    return False


def set_sqlite_fallback_allowed(value: bool) -> None:
    """Reject attempts to re-enable removed SQLite fallback support."""
    if value:
        raise RuntimeError("SQLite fallback support has been removed.")


_postgres_engine: Engine | None = None


def _dispose_management_pool_after_fork() -> None:
    # Dispose before any checkout/pre-ping can touch a parent's socket. Do not
    # close inherited connections: their descriptors still belong to the parent.
    if _postgres_engine is not None:
        _postgres_engine.dispose(close=False)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_dispose_management_pool_after_fork)

def _global_pool_int(key: str, default: int) -> int:
    """Read integer pool setting from env or .env with fallback."""
    raw = runtime_env_value(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _is_pgbouncer_connection_url(url: str) -> bool:
    """Best-effort detection for PgBouncer-backed URLs."""
    env_flag = runtime_env_value("ULTIMA_USE_PGBOUNCER")
    if (env_flag or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query_flag = query.get("pgbouncer", [""])[0].strip().lower()
    pooler = query.get("pooler", [""])[0].strip().lower()
    if query_flag in {"1", "true", "yes", "on"} or pooler == "pgbouncer":
        return True

    if (parsed.hostname or "").strip().lower() == "pgbouncer":
        return True
    if parsed.port == 6432:
        return True
    return False


def _runtime_schema_sync_enabled() -> bool:
    """Legacy escape hatch for runtime DDL outside Alembic.

    Defaults to disabled so Alembic remains the sole schema authority.
    """
    raw = runtime_env_value("ULTIMA_ENABLE_RUNTIME_SCHEMA_SYNC")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _ensure_management_schema_invariants(engine: Engine) -> None:
    """Ensure management settings/backends invariants that code relies on.

    This is idempotent and safe to run at startup for postgres engines.
    """
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS management"))

        settings_exists = conn.execute(
            text("SELECT to_regclass('management.settings') IS NOT NULL")
        ).scalar()
        if not bool(settings_exists):
            _logger.warning(
                "[GlobalDB] management.settings is missing; skipping settings trigger setup"
            )
            return

        # Ensure required columns exist and are populated.
        conn.execute(
            text(
                "ALTER TABLE management.settings "
                "ADD COLUMN IF NOT EXISTS version integer DEFAULT 1"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE management.settings "
                "ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now()"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE management.settings "
                "ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()"
            )
        )
        conn.execute(
            text(
                "UPDATE management.settings "
                "SET version = COALESCE(version, 1), "
                "created_at = COALESCE(created_at, now()), "
                "updated_at = COALESCE(updated_at, now()) "
                "WHERE version IS NULL OR created_at IS NULL OR updated_at IS NULL"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE management.settings "
                "ALTER COLUMN version SET DEFAULT 1, "
                "ALTER COLUMN version SET NOT NULL, "
                "ALTER COLUMN created_at SET DEFAULT now(), "
                "ALTER COLUMN created_at SET NOT NULL, "
                "ALTER COLUMN updated_at SET DEFAULT now(), "
                "ALTER COLUMN updated_at SET NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_settings_id_version ON management.settings (id, version)"
            )
        )

        # Ensure DB-side timestamp/version update behavior.
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION management.touch_settings_row()
                RETURNS trigger AS $$
                BEGIN
                    NEW.updated_at = now();
                    NEW.version = COALESCE(OLD.version, 0) + 1;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        conn.execute(
            text(
                "DROP TRIGGER IF EXISTS trg_settings_touch_update ON management.settings"
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER trg_settings_touch_update
                BEFORE UPDATE ON management.settings
                FOR EACH ROW
                EXECUTE FUNCTION management.touch_settings_row();
                """
            )
        )

        # Backend inventory table (many backends can reference one settings row).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS management.backends (
                    id bigserial PRIMARY KEY,
                    backend_name text NOT NULL,
                    hostname text NOT NULL UNIQUE,
                    local_ip inet NULL,
                    settings_id bigint NOT NULL REFERENCES management.settings(id) ON DELETE RESTRICT,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                );
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_backends_settings_id ON management.backends (settings_id)"
            )
        )
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION management.touch_backends_row()
                RETURNS trigger AS $$
                BEGIN
                    NEW.updated_at = now();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        conn.execute(
            text(
                "DROP TRIGGER IF EXISTS trg_backends_touch_update ON management.backends"
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER trg_backends_touch_update
                BEFORE UPDATE ON management.backends
                FOR EACH ROW
                EXECUTE FUNCTION management.touch_backends_row();
                """
            )
        )


def set_postgres_engine(engine: Engine) -> None:
    """Inject the application-wide postgres engine.

    After this call every ``global_session()`` will use postgres.
    Typically called once during startup after the config has been loaded.
    """
    global _postgres_engine
    _postgres_engine = engine
    if _runtime_schema_sync_enabled():
        try:
            _ensure_management_schema_invariants(engine)
        except Exception as exc:
            _logger.warning(
                "[GlobalDB] Failed to ensure settings/backends invariants: %s", exc
            )
    else:
        _logger.info(
            "[GlobalDB] Runtime schema sync disabled; schema changes must come from Alembic migrations"
        )
    _logger.info("[GlobalDB] Postgres engine set - management schema active")


def set_postgres_url(url: str) -> None:
    """Convenience: create a *sync* postgres engine from a URL and register it.

    The URL should use the synchronous ``postgresql+psycopg://`` driver, e.g.
    ``postgresql+psycopg://user:pass@host:5432/ultima_archive``

    If a bare ``postgresql://`` URL is passed it is automatically rewritten
    to ``postgresql+psycopg://``.
    """
    # This helper creates a synchronous engine. Setup/migrations may persist
    # the same URL with the asyncpg driver, so normalize all supported URL
    # schemes before handing it to SQLAlchemy's sync engine.
    for async_scheme in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql://",
    ):
        if url.startswith(async_scheme):
            url = "postgresql+psycopg://" + url[len(async_scheme) :]
            break

    is_pgbouncer = _is_pgbouncer_connection_url(url)
    pool_mode = (runtime_env_value("ULTIMA_PGBOUNCER_GLOBAL_POOL_MODE") or "unknown").strip().lower()
    if pool_mode not in {"unknown", "session", "transaction"}:
        raise ValueError("ULTIMA_PGBOUNCER_GLOBAL_POOL_MODE must be unknown, session or transaction")
    if is_pgbouncer:
        _logger.info("[GlobalDB] PgBouncer mode detected for the archive database URL")

    engine_kwargs: dict[str, object] = {
        "poolclass": QueuePool,
        "pool_pre_ping": True,
        "pool_size": max(1, _global_pool_int("ULTIMA_GLOBAL_DB_POOL_SIZE", 3)),
        "max_overflow": max(0, _global_pool_int("ULTIMA_GLOBAL_DB_MAX_OVERFLOW", 5)),
    }
    process_role = (
        runtime_env_value("ULTIMA_DATABASE_PROCESS_ROLE") or "application"
    ).strip().lower()
    if process_role not in {"application", "worker_reader", "writer"}:
        raise ValueError(f"Unsupported database process role: {process_role}")
    if process_role == "writer":
        engine_kwargs["pool_size"] = max(
            1, _global_pool_int("ULTIMA_DATABASE_WRITER_CONCURRENCY", 4)
        )
        engine_kwargs["max_overflow"] = 0
    elif is_pgbouncer and pool_mode == "transaction":
        # An operator assertion about this URL's effective user/database mode,
        # never inferred from the port or the pooler's global default.
        engine_kwargs.update(
            pool_size=max(1, _global_pool_int("ULTIMA_PGBOUNCER_GLOBAL_POOL_SIZE", 2)),
            max_overflow=0, pool_timeout=5, pool_use_lifo=True,
            pool_reset_on_return="rollback",
        )
    elif process_role == "worker_reader" or is_pgbouncer:
        # Worker count must not multiply retained client pools. API processes
        # behind PgBouncer also release clients at transaction boundaries.
        engine_kwargs = {"poolclass": NullPool}
    if is_pgbouncer:
        engine_kwargs["connect_args"] = {"prepare_threshold": None}

    engine = create_engine(url, **engine_kwargs)
    # Inherited sockets must never be checked out by a forked child. The
    # parent retains its own descriptor and the child reconnects lazily.
    @event.listens_for(engine, "connect")
    def record_process(connection, record):
        record.info["pid"] = os.getpid()

    @event.listens_for(engine, "checkout")
    def check_process(connection, record, proxy):
        if record.info.get("pid") != os.getpid():
            record.dbapi_connection = proxy.dbapi_connection = None
            raise exc.DisconnectionError("Management connection belongs to another process")

    if engine_kwargs["poolclass"] is QueuePool:
        from .pool_watch import install_pool_watch

        install_pool_watch(engine)

    _logger.info(
        "[GlobalDB] pid=%s role=%s PgBouncer=%s mode=%s pool=%s retained_cap=%s overflow=%s; deployment budget=sum(process caps)",
        os.getpid(), process_role, is_pgbouncer, pool_mode,
        engine_kwargs["poolclass"].__name__, engine_kwargs.get("pool_size", 0),
        engine_kwargs.get("max_overflow", 0),
    )
    set_postgres_engine(engine)


def get_postgres_engine() -> Engine | None:
    """Return the registered postgres engine, or ``None``."""
    return _postgres_engine


def bootstrap_from_env() -> bool:
    """Try to bootstrap the PostgreSQL engine from process or file config.

    Returns ``True`` if postgres was successfully bootstrapped,
    ``False`` if no archive database URL was found or it failed.
    """
    if _postgres_engine is not None:
        return True  # already bootstrapped

    db_url = archive_database_url()
    if not db_url:
        return False

    try:
        set_postgres_url(db_url)
        return True
    except Exception:
        _logger.debug("Could not bootstrap PostgreSQL from runtime configuration")
        return False


# -------------------------------------------------------------------- #
# Unified session factory
# -------------------------------------------------------------------- #


def get_global_engine(
    base_directory: Path | None = None, *, allow_fallback: bool | None = None
) -> Engine:
    """Return the active engine (postgres preferred).

    SQLite fallback support has been removed. If PostgreSQL has not been
    configured, a ``RuntimeError`` is raised.
    """
    # Lazily bootstrap postgres from persisted runtime config so API routes
    # that don't instantiate full backend config still resolve the archive URL.
    if _postgres_engine is None:
        bootstrap_from_env()

    if _postgres_engine is not None:
        return _postgres_engine

    raise RuntimeError(
        "PostgreSQL is not configured. Set ULTIMA_ARCHIVE_DATABASE_URL before accessing the "
        "global database."
    )


def get_global_session() -> Session:
    """Create a new session against the active backend.

    Prefer :func:`global_session` context manager to guarantee cleanup.  This
    wrapper requires PostgreSQL to be configured.
    """
    return Session(get_global_engine())


@contextmanager
def global_session() -> Generator[Session, None, None]:
    """Context manager that yields a :class:`Session` and guarantees cleanup.

    Usage::

        with global_session() as session:
            session.exec(...)
            session.commit()
    """
    session = Session(get_global_engine())
    try:
        yield session
    finally:
        session.close()
