"""Correct existing favourite timestamps and assign chronological integer IDs.

Only the snapshot present during this revision is corrected. Future inserts
retain now()/added defaults and use one shared archive-wide integer sequence.
"""
from alembic import op

revision = "d8f4b2a19c60"
down_revision = "c5f2a8e17d49"
branch_labels = None
depends_on = None

SITES = ("onlyfans", "fansly", "loyalfans")


def upgrade():
    op.execute("SET LOCAL lock_timeout='3s'")
    op.execute("""DO $migration$ BEGIN
        IF NOT pg_try_advisory_xact_lock(hashtextextended('ultima:favourites:cutover',0)) THEN
            RAISE EXCEPTION 'Favourites requests are active; retry the identity migration during an idle window';
        END IF;
        IF NOT pg_try_advisory_xact_lock(hashtextextended('ultima:favourites:migration',0)) THEN
            RAISE EXCEPTION 'A favourites backfill owns the migration lock';
        END IF;
    END $migration$""")
    # Also locks all partitions. Legacy capture waits briefly, then resumes
    # with the new defaults. No users/content table is rewritten or frozen.
    op.execute("LOCK TABLE management.favourites IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $migration$ BEGIN
        IF (SELECT data_type FROM information_schema.columns WHERE table_schema='management'
            AND table_name='favourites' AND column_name='id') IS DISTINCT FROM 'uuid' THEN
            RAISE EXCEPTION 'Expected the UUID favourites schema';
        END IF;
    END $migration$""")

    op.execute("""CREATE TABLE management.favourites_identity_audit (
        site VARCHAR(64) NOT NULL, entity_type VARCHAR(32) NOT NULL, entity_id BIGINT NOT NULL,
        previous_id VARCHAR(64) NOT NULL, previous_created_at TIMESTAMPTZ NOT NULL,
        previous_created_at_source VARCHAR(32) NOT NULL,
        source_downloaded_at TIMESTAMPTZ, source_join_date TIMESTAMPTZ,
        id BIGINT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL, created_at_source VARCHAR(32) NOT NULL,
        PRIMARY KEY (site,entity_type,entity_id)
    )""")
    branches = []
    for site in SITES:
        branches.append(f"""SELECT f.site,f.entity_type,f.entity_id,f.id::text AS previous_id,
            f.created_at AS previous_created_at,f.created_at_source AS previous_created_at_source,
            u.downloaded_at AS source_downloaded_at,u.join_date AS source_join_date,
            coalesce(u.downloaded_at,u.join_date,f.created_at) AS created_at,
            CASE WHEN u.downloaded_at IS NOT NULL THEN 'user_downloaded_at'
                 WHEN u.join_date IS NOT NULL THEN 'user_join_date' ELSE f.created_at_source END AS created_at_source
          FROM management.favourites f LEFT JOIN {site}.users u
            ON f.entity_type='user' AND u.id=f.entity_id WHERE f.site='{site}'""")
    op.execute("""INSERT INTO management.favourites_identity_audit
        (site,entity_type,entity_id,previous_id,previous_created_at,previous_created_at_source,
         source_downloaded_at,source_join_date,id,created_at,created_at_source)
        SELECT site,entity_type,entity_id,previous_id,previous_created_at,previous_created_at_source,
          source_downloaded_at,source_join_date,
          row_number() OVER (ORDER BY created_at ASC,site ASC,entity_type ASC,entity_id ASC),
          created_at,created_at_source FROM (""" + " UNION ALL ".join(branches) + ") snapshot")

    op.execute("ALTER TABLE management.favourites DROP CONSTRAINT ck_favourites_timestamp_source")
    op.execute("""ALTER TABLE management.favourites ADD CONSTRAINT ck_favourites_timestamp_source
        CHECK (created_at_source IN ('added','user_downloaded_at','user_join_date','legacy_favourite','migration_fallback'))""")
    op.execute("ALTER TABLE management.favourites ADD COLUMN integer_id BIGINT")
    op.execute("""UPDATE management.favourites f SET integer_id=a.id,created_at=a.created_at,
        created_at_source=a.created_at_source FROM management.favourites_identity_audit a
        WHERE (f.site,f.entity_type,f.entity_id)=(a.site,a.entity_type,a.entity_id)""")
    op.execute("DROP INDEX management.idx_favourites_chronological")
    op.execute("ALTER TABLE management.favourites DROP CONSTRAINT favourites_pkey")
    op.execute("ALTER TABLE management.favourites DROP COLUMN id")
    op.execute("ALTER TABLE management.favourites RENAME COLUMN integer_id TO id")
    op.execute("ALTER TABLE management.favourites ALTER COLUMN id SET NOT NULL")
    op.execute("ALTER TABLE management.favourites ADD PRIMARY KEY (site,entity_type,id)")
    op.execute("CREATE SEQUENCE management.favourites_id_seq AS BIGINT OWNED BY management.favourites.id")
    op.execute("ALTER TABLE management.favourites ALTER COLUMN id SET DEFAULT nextval('management.favourites_id_seq'::regclass)")
    op.execute("SELECT setval('management.favourites_id_seq',coalesce((SELECT max(id) FROM management.favourites),0)+1,false)")
    op.execute("CREATE INDEX idx_favourites_chronological ON management.favourites (created_at DESC,id DESC)")


def downgrade():
    raise RuntimeError("Retain integer favourites and the identity audit; reverting requires a separately reviewed projection")
