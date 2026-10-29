"""Explicit, resumable favourites cutover. Never invoked during app startup;
setup only calls :func:`activate_empty_sites` for installations with nothing to copy.

Run ``python -m ultima_scraper_db_archive.favourites_migration --help``.
Mutation commands require a direct archive connection and the migration lock.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.pool import NullPool
from ultima_scraper_core import archive_database_url

from .favourites_models import SITES, TARGETS

LOCK = "ultima:favourites:migration"


def preflight(conn: Connection, url: str) -> dict:
    if conn.execute(text("SELECT current_database()")).scalar() != "ultima_archive":
        raise ValueError("Favourites commands require exactly ultima_archive")
    base = make_url(url)
    for site in SITES:
        configured = archive_database_url(site)
        if configured:
            other = make_url(configured)
            # A supplied direct URL may bypass the pooler; all site settings
            # must nevertheless agree with each other on their archive target.
            canonical = make_url(archive_database_url() or url)
            if (other.host, other.port, other.database) != (canonical.host, canonical.port, canonical.database):
                raise ValueError(f"{site} maps to a different archive connection")
        for table in ("users", "favorite_users", *[t for t in TARGETS.values() if t != "users"]):
            if not conn.execute(text("SELECT to_regclass(:table)"), {"table": f"{site}.{table}"}).scalar():
                raise ValueError(f"Missing archive target {site}.{table}")
        timestamp_type = conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema=:site AND table_name='users' AND column_name='join_date'"), {"site": site}).scalar()
        if timestamp_type != "timestamp with time zone":
            raise ValueError(f"{site}.users.join_date must be timestamptz")
    return {"database": base.database, "sites": list(SITES), "timestamp_column": "join_date"}


def capture_sql(site: str) -> list[str]:
    """One-way capture while legacy storage still owns state."""
    assert site in SITES
    return [
        f"""CREATE OR REPLACE FUNCTION management.capture_favourites_{site}_flag()
        RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, management AS $$
        BEGIN
          IF TG_OP='UPDATE' AND NEW.favorite IS NOT DISTINCT FROM OLD.favorite THEN RETURN NEW; END IF;
          IF NEW.favorite OR EXISTS (SELECT 1 FROM {site}.favorite_users WHERE user_id=NEW.id) THEN
            INSERT INTO management.favourites(site,entity_type,entity_id)
            VALUES ('{site}','user',NEW.id) ON CONFLICT (site,entity_type,entity_id) DO NOTHING;
          ELSE
            DELETE FROM management.favourites WHERE site='{site}' AND entity_type='user' AND entity_id=NEW.id;
          END IF;
          RETURN NEW;
        END $$""",
        f"""CREATE OR REPLACE FUNCTION management.capture_favourites_{site}_rows()
        RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, management AS $$
        DECLARE target_id bigint; flag boolean; target_ids bigint[];
        BEGIN
          target_ids := CASE WHEN TG_OP='DELETE' THEN ARRAY[OLD.user_id]
              WHEN TG_OP='UPDATE' THEN ARRAY[OLD.user_id,NEW.user_id] ELSE ARRAY[NEW.user_id] END;
          FOR target_id IN SELECT DISTINCT unnest(target_ids) ORDER BY 1 LOOP
            SELECT favorite INTO flag FROM {site}.users WHERE id=target_id FOR UPDATE;
            IF NOT FOUND THEN CONTINUE; END IF;
            IF flag OR EXISTS (SELECT 1 FROM {site}.favorite_users WHERE user_id=target_id) THEN
              INSERT INTO management.favourites(site,entity_type,entity_id)
              VALUES ('{site}','user',target_id) ON CONFLICT (site,entity_type,entity_id) DO NOTHING;
            ELSE
              DELETE FROM management.favourites WHERE site='{site}' AND entity_type='user' AND entity_id=target_id;
            END IF;
          END LOOP;
          RETURN NULL;
        END $$""",
        f"DROP TRIGGER IF EXISTS capture_favourites_flag ON {site}.users",
        f"CREATE TRIGGER capture_favourites_flag AFTER INSERT OR UPDATE OF favorite ON {site}.users FOR EACH ROW EXECUTE FUNCTION management.capture_favourites_{site}_flag()",
        f"DROP TRIGGER IF EXISTS capture_favourites_rows ON {site}.favorite_users",
        f"CREATE TRIGGER capture_favourites_rows AFTER INSERT OR DELETE OR UPDATE OF user_id ON {site}.favorite_users FOR EACH ROW EXECUTE FUNCTION management.capture_favourites_{site}_rows()",
    ]


def prepare(conn: Connection) -> None:
    # Persist one migration-start instant and install capture on every site
    # before any potentially long concurrent index build. Resume reuses it.
    with conn.begin():
        conn.execute(text("SET LOCAL lock_timeout='3s'"))
        started_at = conn.execute(text("SELECT coalesce(min(started_at),clock_timestamp()) FROM management.favourites_migration")).scalar()
        for site in SITES:
            existing = conn.execute(text("SELECT active FROM management.favourites_migration WHERE site=:site FOR UPDATE"), {"site": site}).scalar()
            if existing:
                raise ValueError("Cannot reinstall legacy capture after activation")
            conn.execute(text("INSERT INTO management.favourites_migration(site,started_at) VALUES (:site,:started_at) ON CONFLICT DO NOTHING"), {"site": site,"started_at": started_at})
            for statement in capture_sql(site):
                conn.execute(text(statement))
    for site in SITES:
        ensure_index(conn, site)


def ensure_index(conn: Connection, site: str) -> None:
    """Also usable before rollback after temporary indexes were cleaned up."""
    assert site in SITES
    # An interrupted invalid concurrent index is removed before retry.
    name = "idx_users_favourites_backfill"
    valid = conn.execute(text("SELECT i.indisvalid FROM pg_index i WHERE i.indexrelid=to_regclass(:name)"), {"name": f"{site}.{name}"}).scalar()
    conn.commit()
    conn.execution_options(isolation_level="AUTOCOMMIT")
    if valid is False:
        conn.execute(text(f"DROP INDEX CONCURRENTLY {site}.{name}"))
    conn.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {site}.users(id) WHERE favorite IS TRUE"))
    conn.rollback()
    conn.execution_options(isolation_level="READ COMMITTED")


def copy_batch(conn: Connection, site: str, batch_size: int = 1000) -> bool:
    if site not in SITES or not 1 <= batch_size <= 10000:
        raise ValueError("Invalid site or batch size")
    with conn.begin():
        checkpoint = conn.execute(text("SELECT * FROM management.favourites_migration WHERE site=:site FOR UPDATE"), {"site": site}).mappings().one()
        if checkpoint["active"]:
            raise ValueError("Backfill is forbidden after activation")
        if checkpoint["complete"]:
            return False
        # Sparse source enumeration uses the partial index and the legacy
        # relationship index. Lock each candidate user before rechecking state.
        ids = conn.execute(text(f"""SELECT id FROM (
            SELECT id FROM {site}.users WHERE favorite IS TRUE AND id>:last
            UNION SELECT user_id AS id FROM {site}.favorite_users WHERE user_id>:last
        ) source ORDER BY id LIMIT :limit"""), {"last": checkpoint["last_user_id"], "limit": batch_size}).scalars().all()
        if not ids:
            conn.execute(text("UPDATE management.favourites_migration SET complete=true WHERE site=:site"), {"site": site})
            return False
        conn.execute(text(f"SELECT id FROM {site}.users WHERE id=ANY(:ids) ORDER BY id FOR UPDATE"), {"ids": ids}).all()
        result = conn.execute(text(f"""INSERT INTO management.favourites(site,entity_type,entity_id,created_at,created_at_source)
            SELECT :site,'user',u.id,coalesce(u.join_date,:fallback),
                CASE WHEN u.join_date IS NULL THEN 'migration_fallback' ELSE 'user_join_date' END
            FROM {site}.users u WHERE u.id=ANY(:ids) AND (u.favorite IS TRUE OR EXISTS (
                SELECT 1 FROM {site}.favorite_users f WHERE f.user_id=u.id))
            ON CONFLICT (site,entity_type,entity_id) DO NOTHING"""),
            {"site": site, "ids": ids, "fallback": checkpoint["started_at"]})
        copied = result.rowcount
        conn.execute(text("""UPDATE management.favourites_migration SET last_user_id=:last,
            copied=copied+:copied,validated=false WHERE site=:site"""), {"site": site, "last": ids[-1], "copied": copied})
    return True


def validation(conn: Connection, site: str) -> dict:
    assert site in SITES
    audit_exists = conn.execute(text("SELECT to_regclass('management.favourites_identity_audit')")).scalar() is not None
    audit_join = """LEFT JOIN management.favourites_identity_audit a
        ON (a.site,a.entity_type,a.entity_id,a.id)=(f.site,f.entity_type,f.entity_id,f.id)""" if audit_exists else ""
    historical_mismatch = """((f.created_at_source='user_join_date' AND f.created_at IS DISTINCT FROM s.join_date)
        OR (f.created_at_source='migration_fallback' AND f.created_at IS DISTINCT FROM
          (SELECT started_at FROM management.favourites_migration WHERE site=:site)))"""
    timestamp_mismatch = (f"""((a.id IS NOT NULL AND (f.created_at IS DISTINCT FROM a.created_at
        OR f.created_at_source IS DISTINCT FROM a.created_at_source))
        OR (a.id IS NULL AND {historical_mismatch}))""" if audit_exists else historical_mismatch)
    foreign_keys = " OR ".join(
        f"(c.conrelid=to_regclass('management.favourites_{site}_{kind}') AND c.confrelid=to_regclass('{site}.{target}') AND c.conname='fk_favourites_{site}_{kind}_target')"
        for kind, target in TARGETS.items()
    )
    row = conn.execute(text(f"""WITH source AS MATERIALIZED (
        SELECT id,join_date FROM {site}.users WHERE favorite IS TRUE
        UNION SELECT u.id,u.join_date FROM {site}.favorite_users l JOIN {site}.users u ON u.id=l.user_id
      ), canonical AS MATERIALIZED (
        SELECT * FROM management.favourites WHERE site=:site AND entity_type='user'
      ) SELECT
        (SELECT count(*) FROM source) AS source_count,
        (SELECT count(*) FROM canonical) AS canonical_count,
        (SELECT count(*) FROM source s WHERE NOT EXISTS (SELECT 1 FROM canonical f WHERE f.entity_id=s.id)) AS missing,
        (SELECT count(*) FROM canonical f WHERE NOT EXISTS (SELECT 1 FROM source s WHERE s.id=f.entity_id)) AS extra,
        (SELECT count(*) FROM canonical f JOIN source s ON s.id=f.entity_id {audit_join}
          WHERE {timestamp_mismatch}) AS timestamp_mismatches,
        (SELECT count(*) FROM canonical WHERE created_at_source='migration_fallback') AS fallback_count,
        (SELECT count(*) FROM {site}.favorite_users l WHERE NOT EXISTS (SELECT 1 FROM {site}.users u WHERE u.id=l.user_id)) AS legacy_orphans,
        (SELECT count(*) FROM (SELECT entity_type,entity_id FROM management.favourites WHERE site=:site
          GROUP BY entity_type,entity_id HAVING count(*)>1) d) AS duplicates,
        (SELECT count(*) FROM pg_constraint c WHERE c.contype='f' AND c.convalidated AND c.confdeltype='c'
          AND ({foreign_keys})) AS validated_target_foreign_keys
      """), {"site": site}).mappings().one()
    return dict(row)


def finish(conn: Connection, activate: bool = False) -> dict:
    report = {}
    with conn.begin():
        # Freeze legacy writers only for final validation/cutover, never for
        # the archive scan or backfill. lock_timeout makes this retryable.
        if activate:
            conn.execute(text("SET LOCAL lock_timeout='3s'"))
            if not conn.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended('ultima:favourites:cutover',0))")).scalar():
                raise ValueError("Favourites requests are active; stop writers and retry cutover")
            # DROP TRIGGER needs AccessExclusiveLock. Take the final lock mode
            # before validation; upgrading later can deadlock with an archive
            # writer that already holds a read lock and is waiting to write.
            for site in SITES:
                conn.execute(text(f"LOCK TABLE {site}.users, {site}.favorite_users IN ACCESS EXCLUSIVE MODE"))
        for site in SITES:
            checkpoint = conn.execute(text("SELECT complete,active FROM management.favourites_migration WHERE site=:site FOR UPDATE"), {"site": site}).mappings().one()
            if checkpoint["active"]:
                if activate:
                    report[site] = {"active": True}
                    continue
                raise ValueError("Legacy comparison is invalid after activation")
            if not checkpoint["complete"]:
                raise ValueError(f"{site} backfill is incomplete")
            counts = validation(conn, site)
            report[site] = counts
            valid = not any(counts[k] for k in ("missing", "extra", "timestamp_mismatches", "legacy_orphans", "duplicates")) and counts["validated_target_foreign_keys"] == len(TARGETS)
            conn.execute(text("UPDATE management.favourites_migration SET validated=:valid WHERE site=:site"), {"site": site, "valid": valid})
            if activate and not valid:
                raise ValueError(f"{site} failed validation: {counts}")
            if activate:
                conn.execute(text(f"DROP TRIGGER IF EXISTS capture_favourites_flag ON {site}.users"))
                conn.execute(text(f"DROP TRIGGER IF EXISTS capture_favourites_rows ON {site}.favorite_users"))
                conn.execute(text("UPDATE management.favourites_migration SET active=true WHERE site=:site"), {"site": site})
    return report


def activate_empty_sites(conn: Connection) -> list[str]:
    """Activate sites that never started a cutover and hold no legacy favourites.

    A new installation has nothing to copy, so it starts canonical. A site with
    legacy favourites, or one whose cutover already started, is left alone: it
    still needs the explicit prepare/backfill/activate run above. Returns the
    sites activated.
    """
    activated = []
    with conn.begin():
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ultima:favourites:cutover',0))"))
        for site in SITES:
            started = conn.execute(text("SELECT 1 FROM management.favourites_migration WHERE site=:site"), {"site": site}).scalar()
            if started:
                continue
            legacy = False
            if conn.execute(text("SELECT to_regclass(:name)"), {"name": f"{site}.users"}).scalar():
                legacy = bool(conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {site}.users WHERE favorite IS TRUE)")).scalar())
            if not legacy and conn.execute(text("SELECT to_regclass(:name)"), {"name": f"{site}.favorite_users"}).scalar():
                legacy = bool(conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {site}.favorite_users)")).scalar())
            if legacy:
                continue
            conn.execute(text("INSERT INTO management.favourites_migration(site,complete,validated,active) VALUES (:site,true,true,true)"), {"site": site})
            activated.append(site)
    return activated


def rollback_projection(conn: Connection) -> None:
    with conn.begin():
        conn.execute(text("SET LOCAL lock_timeout='3s'"))
        if not conn.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended('ultima:favourites:cutover',0))")).scalar():
            raise ValueError("Favourites requests are active; stop writers and retry rollback")
        conn.execute(text("LOCK TABLE management.favourites IN SHARE ROW EXCLUSIVE MODE"))
        for site in SITES:
            conn.execute(text(f"LOCK TABLE {site}.users, {site}.favorite_users IN ACCESS EXCLUSIVE MODE"))
            conn.execute(text(f"DROP TRIGGER IF EXISTS capture_favourites_flag ON {site}.users"))
            conn.execute(text(f"DROP TRIGGER IF EXISTS capture_favourites_rows ON {site}.favorite_users"))
            conn.execute(text(f"""UPDATE {site}.users u SET favorite=false WHERE favorite IS TRUE
                AND NOT EXISTS (SELECT 1 FROM management.favourites f WHERE f.site=:site AND f.entity_type='user' AND f.entity_id=u.id)"""), {"site": site})
            conn.execute(text(f"""UPDATE {site}.users u SET favorite=true FROM management.favourites f
                WHERE f.site=:site AND f.entity_type='user' AND f.entity_id=u.id AND u.favorite IS NOT TRUE"""), {"site": site})
            conn.execute(text(f"""DELETE FROM {site}.favorite_users l WHERE NOT EXISTS (
                SELECT 1 FROM management.favourites f WHERE f.site=:site AND f.entity_type='user' AND f.entity_id=l.user_id)"""), {"site": site})
            conn.execute(text("UPDATE management.favourites_migration SET active=false,complete=false,validated=false,last_user_id=0 WHERE site=:site"), {"site": site})
            for statement in capture_sql(site):
                conn.execute(text(statement))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "prepare", "backfill", "validate", "activate", "activate-empty", "rollback-projection", "cleanup-indexes", "recovery-indexes"))
    parser.add_argument("--url-file", type=Path, help="Private file containing a direct ultima_archive URL")
    parser.add_argument("--writers-stopped", action="store_true", help="Confirm coordinated cutover/rollback maintenance")
    parser.add_argument("--batch-size", type=int, default=1000, choices=range(1,10001), metavar="1..10000")
    args = parser.parse_args()
    if args.action in {"activate", "rollback-projection"} and not args.writers_stopped:
        parser.error("Cutover/rollback requires --writers-stopped during coordinated maintenance")
    url = args.url_file.read_text().strip() if args.url_file else archive_database_url()
    if not url:
        parser.error("No archive connection configured")
    parsed = make_url(url)
    if args.action != "preview" and (parsed.port == 6432 or parsed.host == "pgbouncer"):
        parser.error("Mutation commands require a direct connection, not transaction-pooled PgBouncer")
    engine = create_engine(parsed.set(drivername="postgresql+psycopg"), poolclass=NullPool)
    with engine.connect() as conn:
        details = preflight(conn, url)
        conn.commit()
        if args.action == "preview":
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                details["estimates"] = [dict(r) for r in conn.execute(text("""SELECT n.nspname AS site,c.relname AS entity,c.reltuples::bigint AS estimated_rows
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(:sites)
                    AND c.relname IN ('users','favorite_users','x_posts','x_stories','x_messages')"""), {"sites": list(SITES)}).mappings()]
                details["checkpoints"] = [dict(r) for r in conn.execute(text("SELECT * FROM management.favourites_migration")).mappings()] if conn.execute(text("SELECT to_regclass('management.favourites_migration')")).scalar() else []
        else:
            locked = conn.execute(text("SELECT pg_try_advisory_lock(hashtextextended(:key,0))"), {"key": LOCK}).scalar()
            conn.commit()
            if not locked:
                raise RuntimeError("Another favourites migration holds the lock")
            try:
                if args.action == "prepare": prepare(conn)
                elif args.action == "recovery-indexes":
                    for site in SITES: ensure_index(conn, site)
                elif args.action == "backfill":
                    for site in SITES:
                        while copy_batch(conn, site, args.batch_size):
                            checkpoint = conn.execute(text("SELECT last_user_id,copied,started_at FROM management.favourites_migration WHERE site=:site"), {"site": site}).mappings().one()
                            conn.rollback()
                            print(json.dumps({"site": site, "progress": "batch committed", **dict(checkpoint)}, default=str), flush=True)
                elif args.action in ("validate", "activate"): details["validation"] = finish(conn, args.action == "activate")
                elif args.action == "activate-empty": details["activated"] = activate_empty_sites(conn)
                elif args.action == "rollback-projection": rollback_projection(conn)
                elif args.action == "cleanup-indexes":
                    active = conn.execute(text("SELECT count(*) FROM management.favourites_migration WHERE active")).scalar()
                    conn.commit()
                    if active != len(SITES): raise ValueError("Cleanup requires complete activation")
                    conn.execution_options(isolation_level="AUTOCOMMIT")
                    for site in SITES: conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {site}.idx_users_favourites_backfill"))
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"), {"key": LOCK})
                conn.commit()
        print(json.dumps(details, default=str, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
