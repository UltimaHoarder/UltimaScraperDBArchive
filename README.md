# UltimaScraperDBArchive

UltimaScraperDBArchive is the archive database module hosted by the domain-neutral
`ultima-scraper-db` runtime. It owns archive models and constructs `ArchiveAPI`;
it does not own engine or session lifecycle.

```python
from ultima_scraper_db import DatabaseConfig, DatabaseManager
from ultima_scraper_db_archive import USDBArchiveModule

mounted = await DatabaseManager().run(
    USDBArchiveModule(),
    DatabaseConfig(url=database_url),
)
archive_api = mounted.api
```

The package is PostgreSQL-only. Legacy SQLite models remain available solely
for migration compatibility.

## Packaged migration interface

`usdb-archive-migrate check|upgrade` is the only production schema writer for
`ultima_archive`. It reads a mode-0600 URL file, verifies the exact database,
rejects unknown revisions and privileged cluster roles, serializes with a
PostgreSQL advisory lock, and emits a JSON report.

```bash
usdb-archive-migrate check \
  --database-url-file /protected/archive_database_url \
  --expected-head d8f4b2a19c60

usdb-archive-migrate upgrade \
  --database-url-file /protected/archive_database_url \
  --expected-head d8f4b2a19c60
```

The expected head must exactly match the packaged single-head Alembic graph.
