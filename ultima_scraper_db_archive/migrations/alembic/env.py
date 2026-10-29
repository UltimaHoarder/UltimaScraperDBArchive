import asyncio
import logging
from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.sqltypes import Text as SQLAlchemyText

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

from ultima_scraper_core import archive_database_url, runtime_env_value

from ultima_scraper_db_archive.alembic_support import normalize_postgresql_reflection
from ultima_scraper_db_archive.favourites_alembic import compare_favourites_server_default
from ultima_scraper_db_archive.history_alembic import (
    include_name,
    is_runtime_history_leaf,
    is_transient_concurrent_index,
)
from ultima_scraper_db_archive.crypto import EncryptedText
from ultima_scraper_db_archive import execution_models  # noqa: F401 - register management ledger tables
from ultima_scraper_db_archive import plugin_models  # noqa: F401 - register plugin authority
from ultima_scraper_db_archive.favourites_models import partition_names
from ultima_scraper_db_archive.databases.ultima_archive.schemas.templates.postgres_site import (
    merged_metadata,
)

if config.attributes.get("connection") is None:
    # Migrations run as the table owner. When the application connects as a
    # DML-only runtime role, ULTIMA_ARCHIVE_OWNER_DATABASE_URL names the owner.
    db_url = runtime_env_value("ULTIMA_ARCHIVE_OWNER_DATABASE_URL") or archive_database_url()
    if db_url:
        if db_url.startswith("postgresql://"):
            db_url = "postgresql+asyncpg://" + db_url[len("postgresql://") :]
        elif "psycopg" in db_url:
            db_url = db_url.replace("psycopg", "asyncpg")
        config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

# Interpret the config file for Python logging, but only for a standalone run.
# fileConfig clears root handlers and disables existing loggers, so a host
# process that already configured logging (the API's setup migrations) keeps
# its own configuration instead of silently losing its application logs.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = merged_metadata

# Schemas we manage — everything else is ignored by autogenerate.
_MANAGED_SCHEMAS: set[str | None] = {t.schema for t in target_metadata.tables.values()}


def _is_encrypted_text_instance(obj: object) -> bool:
    if isinstance(obj, EncryptedText):
        return True
    cls = getattr(obj, "__class__", None)
    return bool(
        cls
        and cls.__name__ == "EncryptedText"
        and str(getattr(cls, "__module__", "")).endswith(".crypto")
    )


def include_object(
    object: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Only include objects from schemas we explicitly manage."""
    if type_ == "table":
        table_schema = getattr(object, "schema", None)
        # These leaves carry explicit site/type-specific foreign keys. Their
        # lifecycle belongs to the favourites Alembic revision, not autogen.
        if table_schema == "management" and name in partition_names():
            return False
        # Runtime leaves are managed by explicit partition lifecycle, never by
        # autogeneration as unexpected tables to drop. include_name already
        # skips them before reflection; this guards callers without it.
        if (
            reflected
            and compare_to is None
            and table_schema == "management"
            and is_runtime_history_leaf(name)
        ):
            return False
        return table_schema in _MANAGED_SCHEMAS
    if type_ == "column":
        table = getattr(object, "table", None)
        if table is not None:
            return getattr(table, "schema", None) in _MANAGED_SCHEMAS
    if type_ == "index":
        if name == "idx_users_favourites_backfill":
            return False  # Explicit migration CLI owns this temporary index.
        if is_transient_concurrent_index(name):
            return False  # Ignore transient indexes built by concurrent reindexing.
    return True


def compare_type(
    _context: object,
    _inspected_column: object,
    _metadata_column: object,
    inspected_type: object,
    metadata_type: object,
) -> bool | None:
    """Ignore EncryptedText-vs-TEXT diffs (same physical DB storage)."""
    metadata_column_type = getattr(_metadata_column, "type", None)
    if (
        _is_encrypted_text_instance(metadata_column_type)
        or _is_encrypted_text_instance(metadata_type)
    ) and isinstance(inspected_type, SQLAlchemyText):
        return False
    return None


def render_item(
    type_: str,
    obj: Any,
    autogen_context: AutogenContext,
) -> str | Literal[False]:
    """Render EncryptedText as sa.TEXT() in generated migrations."""
    if type_ == "type" and _is_encrypted_text_instance(obj):
        autogen_context.imports.add("import sqlalchemy as sa")
        return "sa.TEXT()"
    return False


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        compare_server_default=compare_favourites_server_default,
        compare_type=compare_type,
        render_item=render_item,
        version_table=config.attributes.get("usdb_version_table", "alembic_version"),
        version_table_schema=config.attributes.get(
            "usdb_version_table_schema", "public"
        ),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # A transaction-pooled PgBouncer connection may arrive with stale
    # site-specific session state. SQLAlchemy caches current_schema() while
    # initializing the connection. Configure Alembic first, then normalize
    # inside Alembic's transaction so SET LOCAL does not create an external
    # transaction that breaks migration autocommit blocks.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        compare_server_default=compare_favourites_server_default,
        compare_type=compare_type,
        render_item=render_item,
        version_table=config.attributes.get("usdb_version_table", "alembic_version"),
        version_table_schema=config.attributes.get(
            "usdb_version_table_schema", "public"
        ),
    )

    with context.begin_transaction():
        normalize_postgresql_reflection(connection)
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    section = config.get_section(config.config_ini_section, {})
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise RuntimeError("sqlalchemy.url is not configured for Alembic")
    section["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        do_run_migrations(supplied_connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
