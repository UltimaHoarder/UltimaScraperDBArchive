"""Guarded JSON CLI for the ``ultima_archive`` Alembic graph."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn, Sequence
from urllib.parse import parse_qsl, urlsplit

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from .module import MIGRATION_BUNDLE

DATABASE = "ultima_archive"
LOCK_NAME = "osr:ultima_archive:migration"
POSTGRES_SCHEMES = frozenset(
    {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg"}
)
ROUTING_QUERY_KEYS = frozenset(
    {
        "database",
        "dbname",
        "host",
        "hostaddr",
        "passfile",
        "password",
        "port",
        "service",
        "servicefile",
        "user",
    }
)


class MigrationRejected(RuntimeError):
    """A migration safety contract was not satisfied."""


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise MigrationRejected(message)


@dataclass(frozen=True, slots=True)
class MigrationReport:
    action: str
    database: str
    role: str
    before: tuple[str, ...]
    expected: tuple[str, ...]
    after: tuple[str, ...]
    changed: bool
    status: str


def _read_url_file(path: Path) -> str:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise MigrationRejected("database URL file must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MigrationRejected("database URL file does not exist") from exc
    file_stat = resolved.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise MigrationRejected("database URL file must be regular")
    if stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise MigrationRejected("database URL file must be mode 0600")
    value = resolved.read_text(encoding="utf-8").strip()
    parsed = urlsplit(value)
    query_keys = {
        key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if (
        parsed.scheme not in POSTGRES_SCHEMES
        or not parsed.hostname
        or not parsed.username
        or parsed.fragment
        or parsed.path.lstrip("/") != DATABASE
        or query_keys & ROUTING_QUERY_KEYS
    ):
        raise MigrationRejected(f"migration target must be exactly {DATABASE}")
    return value


def _sync_url(value: str) -> str:
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + value.removeprefix(
            "postgresql+asyncpg://"
        )
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    return value


def _graph() -> tuple[frozenset[str], frozenset[str]]:
    config = MIGRATION_BUNDLE.create_config("postgresql://unused/unused")
    graph = ScriptDirectory.from_config(config)
    known = frozenset(revision.revision for revision in graph.walk_revisions())
    heads = frozenset(graph.get_heads())
    if len(heads) != 1:
        raise MigrationRejected(f"migration package has unexpected heads: {sorted(heads)}")
    return known, heads


def _validate_expected_head(expected_head: str, heads: frozenset[str]) -> None:
    if frozenset({expected_head}) != heads:
        raise MigrationRejected(
            "requested head does not match the packaged migration graph"
        )


def _validate_role(connection: Connection) -> str:
    row = connection.execute(
        text(
            """
            SELECT current_user, current_database(), rolsuper, rolcreaterole,
                   rolcreatedb, rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
    ).one()
    role = str(row[0])
    if str(row[1]) != DATABASE:
        raise MigrationRejected(f"connected database must be exactly {DATABASE}")
    privilege_names = (
        "superuser",
        "create-role",
        "create-database",
        "replication",
        "bypass-rls",
    )
    granted = [name for name, enabled in zip(privilege_names, row[2:]) if enabled]
    if granted:
        raise MigrationRejected(
            "migration role has forbidden cluster privileges: " + ", ".join(granted)
        )
    connection.commit()
    return role


def _revisions(connection: Connection) -> frozenset[str]:
    exists = connection.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar_one()
    if exists is None:
        connection.commit()
        return frozenset()
    revisions = frozenset(
        str(row[0])
        for row in connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        )
    )
    connection.commit()
    return revisions


def _validate_revisions(revisions: frozenset[str], known: frozenset[str]) -> None:
    unknown = revisions - known
    if unknown:
        raise MigrationRejected(f"unknown starting revisions: {sorted(unknown)}")


def _acquire_lock(connection: Connection) -> None:
    locked = bool(
        connection.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:name))"), {"name": LOCK_NAME}
        ).scalar_one()
    )
    connection.commit()
    if not locked:
        raise MigrationRejected("another migration owns the database advisory lock")


def _release_lock(connection: Connection) -> None:
    if connection.in_transaction():
        connection.rollback()
    unlocked = bool(
        connection.execute(
            text("SELECT pg_advisory_unlock(hashtext(:name))"), {"name": LOCK_NAME}
        ).scalar_one()
    )
    connection.commit()
    if not unlocked:
        raise MigrationRejected("database advisory lock was lost")


def run(action: str, url_file: Path, expected_head: str) -> MigrationReport:
    if action not in {"check", "upgrade"}:
        raise MigrationRejected(f"unsupported migration action: {action}")
    database_url = _read_url_file(url_file)
    known, heads = _graph()
    _validate_expected_head(expected_head, heads)
    engine = create_engine(_sync_url(database_url), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            role = _validate_role(connection)
            _acquire_lock(connection)
            try:
                before = _revisions(connection)
                _validate_revisions(before, known)
                if action == "upgrade":
                    config = MIGRATION_BUNDLE.create_config(database_url)
                    config.attributes["connection"] = connection
                    command.upgrade(config, "heads")
                    if connection.in_transaction():
                        connection.commit()
                after = _revisions(connection)
                _validate_revisions(after, known)
                if action == "upgrade" and after != heads:
                    raise MigrationRejected(
                        f"unexpected final heads: {sorted(after)}"
                    )
                status = "current" if after == heads else "upgrade-required"
                return MigrationReport(
                    action=action,
                    database=DATABASE,
                    role=role,
                    before=tuple(sorted(before)),
                    expected=tuple(sorted(heads)),
                    after=tuple(sorted(after)),
                    changed=before != after,
                    status=status,
                )
            finally:
                _release_lock(connection)
    finally:
        engine.dispose()


def _parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="usdb-archive-migrate")
    parser.add_argument("action", choices=("check", "upgrade"))
    parser.add_argument("--database-url-file", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        report = run(args.action, args.database_url_file, args.expected_head)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "action": "rejected",
                    "database": DATABASE,
                    "error": str(exc),
                    "status": "error",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(asdict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
