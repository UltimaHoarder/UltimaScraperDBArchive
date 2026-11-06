from __future__ import annotations

import inspect
import subprocess
import sys
from typing import Any

from alembic.script import ScriptDirectory
from ultima_scraper_db import DatabaseDefinition

from ultima_scraper_db_archive import MIGRATION_BUNDLE, ArchiveAPI, USDBArchiveModule


def test_archive_exposes_an_opaque_usdb_module() -> None:
    module = USDBArchiveModule()

    assert isinstance(module.definition, DatabaseDefinition)
    assert module.definition.key == "usdb-archive"
    assert module.definition.migrations is MIGRATION_BUNDLE
    assert MIGRATION_BUNDLE.config_path.is_file()
    assert "management" in module.definition.schemas
    assert "pg_trgm" in module.definition.required_extensions
    assert module.definition.optional_extensions == ("vector",)


def test_archive_constructs_its_own_domain_api() -> None:
    module = USDBArchiveModule()
    handle: Any = object()

    api = module.create_api(handle)

    assert isinstance(api, ArchiveAPI)
    assert api.database is handle


def test_archive_does_not_import_the_usr_backend() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ultima_scraper_db_archive; "
                "assert 'ultima_scraper_backend' not in sys.modules"
            ),
        ],
        check=True,
    )


def test_archive_head_owns_search_loadout_schema_and_sequence_repair() -> None:
    config = MIGRATION_BUNDLE.create_config(
        "postgresql+psycopg://unused:unused@localhost/ultima_archive"
    )
    graph = ScriptDirectory.from_config(config)

    # One head, and this repair is part of the chain leading to it; later
    # migrations build on top of it.
    heads = graph.get_heads()
    assert len(heads) == 1
    chain = {step.revision for step in graph.iterate_revisions(heads[0], "base")}
    assert "7a2d9c4e1f80" in chain
    revision = graph.get_revision("7a2d9c4e1f80")
    assert revision is not None
    assert revision.down_revision == "f6a1c8e29b47"
    source = inspect.getsource(revision.module.upgrade)
    assert "management.search_loadouts" in source
    assert "setval" in source
    assert "content_media_asso" in revision.module.RUNTIME_SEQUENCE_TABLES
    assert "filepaths" in revision.module.RUNTIME_SEQUENCE_TABLES
