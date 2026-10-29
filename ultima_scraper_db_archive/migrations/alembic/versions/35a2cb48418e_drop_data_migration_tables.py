"""Drop the data migration tool's tables.

Revision ID: 35a2cb48418e
Revises: baa73c9d688e

The Data Migration and AI / Ledger Review tools are removed, along with the
source-identity observations every profile sync recorded for them. The
upgrade permanently deletes their rows; downgrade recreates the tables empty.

Dropping ``migration_import_claims`` removes its foreign key to
``database_write_receipts``, which briefly takes an exclusive lock on the
receipts table. Apply it after the backend that no longer writes these tables
is running; an older backend fails its profile writes once they are gone.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "35a2cb48418e"
down_revision: Union[str, Sequence[str], None] = "baa73c9d688e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Children before the claims table they reference.
TABLES = (
    "migration_projection_keys",
    "migration_claim_identities",
    "migration_import_claims",
    "migration_source_identities",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS management.{table}")


def downgrade() -> None:
    op.execute("""
CREATE TABLE management.migration_source_identities (
    site character varying(64) NOT NULL,
    identity_type character varying(16) NOT NULL,
    identity_key text NOT NULL,
    authoritative_user_id bigint,
    observation_id character varying(32),
    authority text,
    observed_at timestamp with time zone,
    CONSTRAINT migration_source_identities_pkey
        PRIMARY KEY (site, identity_type, identity_key)
)""")
    op.execute("""
CREATE TABLE management.migration_import_claims (
    claim_id character varying(32) NOT NULL,
    command_id character varying(128) NOT NULL,
    outcome_id character varying(32) NOT NULL,
    state_store_id character varying(32),
    ledger_id text NOT NULL,
    generation_id character varying(32) NOT NULL,
    source_root text NOT NULL,
    site character varying(64) NOT NULL,
    target_table character varying(64) NOT NULL,
    target_id bigint NOT NULL,
    performer_claim_id character varying(32),
    entry_json text NOT NULL,
    authority_json text,
    ledger_finalized boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT migration_import_claims_pkey PRIMARY KEY (claim_id),
    CONSTRAINT uq_migration_claim_outcome_ledger UNIQUE (outcome_id, ledger_id),
    CONSTRAINT migration_import_claims_command_id_fkey FOREIGN KEY (command_id)
        REFERENCES management.database_write_receipts(command_id),
    CONSTRAINT migration_import_claims_performer_claim_id_fkey
        FOREIGN KEY (performer_claim_id)
        REFERENCES management.migration_import_claims(claim_id)
)""")
    op.execute("""
CREATE TABLE management.migration_projection_keys (
    site character varying(64) NOT NULL,
    target_table character varying(64) NOT NULL,
    target_id bigint NOT NULL,
    claim_id character varying(32) NOT NULL,
    authority_json text,
    CONSTRAINT migration_projection_keys_pkey
        PRIMARY KEY (site, target_table, target_id, claim_id),
    CONSTRAINT migration_projection_keys_claim_id_fkey FOREIGN KEY (claim_id)
        REFERENCES management.migration_import_claims(claim_id)
)""")
    op.execute("""
CREATE TABLE management.migration_claim_identities (
    site character varying(64) NOT NULL,
    username text NOT NULL,
    claim_id character varying(32) NOT NULL,
    CONSTRAINT migration_claim_identities_pkey PRIMARY KEY (site, username, claim_id),
    CONSTRAINT migration_claim_identities_claim_id_fkey FOREIGN KEY (claim_id)
        REFERENCES management.migration_import_claims(claim_id)
)""")
    for statement in (
        "CREATE INDEX idx_migration_claim_generation ON management.migration_import_claims "
        "(site, ledger_id, generation_id, claim_id)",
        "CREATE INDEX idx_migration_claim_owner_authority ON management.migration_import_claims "
        "(state_store_id, site, claim_id) "
        "WHERE authority_json IS NOT NULL AND NOT ledger_finalized",
        "CREATE INDEX idx_migration_claim_parent ON management.migration_import_claims "
        "(performer_claim_id, claim_id)",
        "CREATE INDEX idx_migration_claim_source ON management.migration_import_claims "
        "(site, source_root, claim_id)",
        "CREATE INDEX idx_migration_claim_unpublished_authority "
        "ON management.migration_import_claims (site, claim_id) "
        "WHERE authority_json IS NOT NULL AND NOT ledger_finalized",
        "CREATE INDEX idx_migration_identity_claim ON management.migration_claim_identities "
        "(claim_id)",
        "CREATE INDEX idx_migration_projection_claim ON management.migration_projection_keys "
        "(claim_id, target_table, target_id)",
    ):
        op.execute(statement)
