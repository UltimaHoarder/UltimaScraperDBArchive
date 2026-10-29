"""Add shared, partitioned favourites with native target cascades.

The separately invoked favourites migration CLI owns capture and backfill.
"""
from alembic import op

revision = "ce84a19f027b"
down_revision = "f3c81d2a6e57"
branch_labels = None
depends_on = None

SITES = ("onlyfans", "fansly", "loyalfans")
TARGETS = {"user": "users", "post": "x_posts", "story": "x_stories", "message": "x_messages"}


def upgrade():
    op.execute("""CREATE TABLE management.favourites (
        site VARCHAR(64) NOT NULL, entity_type VARCHAR(32) NOT NULL,
        id UUID NOT NULL DEFAULT gen_random_uuid(), entity_id BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at_source VARCHAR(32) NOT NULL DEFAULT 'added',
        PRIMARY KEY (site, entity_type, id),
        CONSTRAINT uq_favourites_entity UNIQUE (site, entity_type, entity_id),
        CONSTRAINT ck_favourites_timestamp_source CHECK (created_at_source IN
            ('added','user_join_date','legacy_favourite','migration_fallback'))
    ) PARTITION BY LIST (site)""")
    for site in SITES:
        op.execute(f"CREATE TABLE management.favourites_{site} PARTITION OF management.favourites FOR VALUES IN ('{site}') PARTITION BY LIST (entity_type)")
        for kind, table in TARGETS.items():
            name = f"favourites_{site}_{kind}"
            op.execute(f"CREATE TABLE management.{name} PARTITION OF management.favourites_{site} FOR VALUES IN ('{kind}')")
            op.execute(f"ALTER TABLE management.{name} ADD CONSTRAINT fk_{name}_target FOREIGN KEY (entity_id) REFERENCES {site}.{table}(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX idx_favourites_chronological ON management.favourites (created_at DESC, id DESC)")
    op.execute("""CREATE TABLE management.favourites_migration (
        site VARCHAR(64) PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_user_id BIGINT NOT NULL DEFAULT 0, copied BIGINT NOT NULL DEFAULT 0,
        complete BOOLEAN NOT NULL DEFAULT false, validated BOOLEAN NOT NULL DEFAULT false,
        active BOOLEAN NOT NULL DEFAULT false
    )""")


def downgrade():
    # Keep canonical data recoverable. A reviewed export/projection must precede
    # removal; a routine Alembic downgrade cannot silently discard favourites.
    raise RuntimeError("Project/export canonical favourites with favourites_migration before a reviewed schema removal")
