"""USDB module adapter for the archive database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncSession
from ultima_scraper_db import (
    DatabaseDefinition,
    DatabaseHandle,
    MigrationBundle,
)

MIGRATION_BUNDLE = MigrationBundle(Path(__file__).parent / "migrations")


def _managed_schemas(metadata: MetaData) -> tuple[str, ...]:
    """Return the schemas explicitly owned by the archive module."""

    return tuple(
        sorted(
            {
                table.schema
                for table in metadata.tables.values()
                if table.schema is not None
            }
        )
    )


class ArchiveAPI:
    """Archive-facing API root backed by a generic USDB database handle.

    Domain repositories will attach to this root as they move out of BackendMini.
    Until then it provides safe session and schema-transaction boundaries without
    teaching the USDB runtime what a site or archive is.
    """

    def __init__(
        self,
        database: DatabaseHandle,
        schemas: tuple[str, ...],
    ) -> None:
        self.database = database
        self.schemas = frozenset(schemas)

    def session(self):
        """Create a short-lived archive session."""

        return self.database.session()

    @asynccontextmanager
    async def schema_transaction(self, schema: str) -> AsyncIterator[AsyncSession]:
        """Run a transaction with a validated archive schema on the search path."""

        normalized = schema.lower()
        if normalized not in self.schemas:
            raise ValueError(f"Archive schema is not managed: {schema}")

        async with self.database.transaction() as session:
            bind = session.get_bind()
            quoted_schema = bind.dialect.identifier_preparer.quote(normalized)
            await session.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}, public")
            )
            yield session


class USDBArchiveModule:
    """Mount archive metadata and its API through the generic USDB runtime."""

    def __init__(
        self,
        *,
        migrations: MigrationBundle | None = MIGRATION_BUNDLE,
    ) -> None:
        from .databases.ultima_archive.schemas.templates.postgres_site import (
            merged_metadata,
        )

        schemas = _managed_schemas(merged_metadata)
        self.definition = DatabaseDefinition(
            key="usdb-archive",
            metadata=merged_metadata,
            migrations=migrations,
            required_extensions=("uuid-ossp", "pg_trgm"),
            optional_extensions=("vector",),
            schemas=schemas,
        )

    def create_api(self, database: DatabaseHandle) -> ArchiveAPI:
        return ArchiveAPI(database, self.definition.schemas)
