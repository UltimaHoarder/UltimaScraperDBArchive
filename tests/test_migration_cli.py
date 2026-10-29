from __future__ import annotations

import os
from pathlib import Path

import pytest

from ultima_scraper_db_archive.migration_cli import (
    MigrationRejected,
    _acquire_lock,
    _read_url_file,
    _sync_url,
    _validate_expected_head,
    _validate_role,
    _validate_revisions,
)


def _secret(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "database-url"
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_database_url_file_is_strict(tmp_path: Path) -> None:
    path = _secret(
        tmp_path,
        "postgresql://ultimascraper:secret@postgres.private.internal/ultima_archive",
    )
    assert "ultima_archive" in _read_url_file(path)
    path.chmod(0o640)
    with pytest.raises(MigrationRejected, match="mode 0600"):
        _read_url_file(path)


def test_database_url_file_rejects_symlink(tmp_path: Path) -> None:
    target = _secret(
        tmp_path,
        "postgresql://ultimascraper:secret@postgres.private.internal/ultima_archive",
    )
    link = tmp_path / "linked-url"
    os.symlink(target, link)
    with pytest.raises(MigrationRejected, match="symlink"):
        _read_url_file(link)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://ultimascraper:secret@postgres/ultima_panel",
        "postgresql://ultimascraper:secret@postgres/ultima_archive?dbname=other",
        "sqlite:///ultima_archive",
    ],
)
def test_database_url_rejects_wrong_or_rerouted_target(
    tmp_path: Path, url: str
) -> None:
    with pytest.raises(MigrationRejected, match="exactly ultima_archive"):
        _read_url_file(_secret(tmp_path, url))


def test_revision_guards_reject_unknown_and_mismatched_head() -> None:
    with pytest.raises(MigrationRejected, match="unknown starting"):
        _validate_revisions(frozenset({"foreign"}), frozenset({"known"}))
    with pytest.raises(MigrationRejected, match="packaged migration graph"):
        _validate_expected_head("wrong", frozenset({"right"}))


def test_async_url_is_normalized_for_guard_connection() -> None:
    assert _sync_url("postgresql+asyncpg://u:p@db/name") == (
        "postgresql+psycopg://u:p@db/name"
    )


class _Result:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value

    def one(self) -> object:
        return self.value


class _Connection:
    def __init__(self, values: list[object]) -> None:
        self.values = iter(values)

    def execute(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result(next(self.values))

    def commit(self) -> None:
        pass


def test_concurrent_migration_lock_is_rejected() -> None:
    with pytest.raises(MigrationRejected, match="another migration"):
        _acquire_lock(_Connection([False]))  # type: ignore[arg-type]


def test_privileged_cluster_role_is_rejected() -> None:
    role = ("ultimascraper", "ultima_archive", True, False, False, False, False)
    with pytest.raises(MigrationRejected, match="superuser"):
        _validate_role(_Connection([role]))  # type: ignore[arg-type]


def test_transient_concurrent_indexes_are_skipped() -> None:
    from ultima_scraper_db_archive.history_alembic import (
        include_name,
        is_transient_concurrent_index,
    )

    assert is_transient_concurrent_index("execution_work_payloads_pkey_ccnew") is True
    assert is_transient_concurrent_index("execution_work_payloads_pkey_ccold") is True
    assert is_transient_concurrent_index("execution_work_payloads_pkey") is False
    assert is_transient_concurrent_index(None) is False

    assert include_name("execution_work_payloads_pkey_ccnew", "index", {}) is False
    assert include_name("execution_work_payloads_pkey_ccold", "index", {}) is False
    assert include_name("execution_work_payloads_pkey", "index", {}) is True

