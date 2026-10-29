"""Retain import claims and projection membership with PostgreSQL transactions.

Revision ID: e5b72c1a09f4
Revises: f14c08a932de
"""

from alembic import op
import sqlalchemy as sa


revision = "e5b72c1a09f4"
down_revision = "f14c08a932de"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "migration_import_claims",
        sa.Column("claim_id", sa.String(32), primary_key=True),
        sa.Column(
            "command_id",
            sa.String(128),
            sa.ForeignKey("management.database_write_receipts.command_id"),
            nullable=False,
        ),
        sa.Column("outcome_id", sa.String(32), nullable=False),
        sa.Column("state_store_id", sa.String(32), nullable=True),
        sa.Column("ledger_id", sa.Text(), nullable=False),
        sa.Column("generation_id", sa.String(32), nullable=False),
        sa.Column("source_root", sa.Text(), nullable=False),
        sa.Column("site", sa.String(64), nullable=False),
        sa.Column("target_table", sa.String(64), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "performer_claim_id",
            sa.String(32),
            sa.ForeignKey("management.migration_import_claims.claim_id"),
            nullable=True,
        ),
        sa.Column("entry_json", sa.Text(), nullable=False),
        sa.Column("authority_json", sa.Text(), nullable=True),
        sa.Column(
            "ledger_finalized", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "outcome_id", "ledger_id", name="uq_migration_claim_outcome_ledger"
        ),
        schema="management",
    )
    for name, columns in (
        ("idx_migration_claim_source", ["site", "source_root", "claim_id"]),
        (
            "idx_migration_claim_generation",
            ["site", "ledger_id", "generation_id", "claim_id"],
        ),
        ("idx_migration_claim_parent", ["performer_claim_id", "claim_id"]),
    ):
        op.create_index(name, "migration_import_claims", columns, schema="management")
    op.create_index(
        "idx_migration_claim_unpublished_authority",
        "migration_import_claims",
        ["site", "claim_id"],
        schema="management",
        postgresql_where=sa.text("authority_json IS NOT NULL AND NOT ledger_finalized"),
    )
    op.create_index(
        "idx_migration_claim_owner_authority",
        "migration_import_claims",
        ["state_store_id", "site", "claim_id"],
        schema="management",
        postgresql_where=sa.text("authority_json IS NOT NULL AND NOT ledger_finalized"),
    )
    op.create_table(
        "migration_projection_keys",
        sa.Column("site", sa.String(64), primary_key=True),
        sa.Column("target_table", sa.String(64), primary_key=True),
        sa.Column("target_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(32),
            sa.ForeignKey("management.migration_import_claims.claim_id"),
            primary_key=True,
        ),
        sa.Column("authority_json", sa.Text(), nullable=True),
        schema="management",
    )
    op.create_index(
        "idx_migration_projection_claim",
        "migration_projection_keys",
        ["claim_id", "target_table", "target_id"],
        schema="management",
    )
    op.create_table(
        "migration_claim_identities",
        sa.Column("site", sa.String(64), primary_key=True),
        sa.Column("username", sa.Text(), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(32),
            sa.ForeignKey("management.migration_import_claims.claim_id"),
            primary_key=True,
        ),
        schema="management",
    )
    op.create_index(
        "idx_migration_identity_claim",
        "migration_claim_identities",
        ["claim_id"],
        schema="management",
    )


def downgrade():
    op.drop_table("migration_claim_identities", schema="management")
    op.drop_table("migration_projection_keys", schema="management")
    op.drop_table("migration_import_claims", schema="management")
