"""Fence first import claims against durable source identity observations.

Revision ID: a92e10b6f3d8
Revises: e5b72c1a09f4
"""

from alembic import op
import sqlalchemy as sa

revision = "a92e10b6f3d8"
down_revision = "e5b72c1a09f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "migration_source_identities",
        sa.Column("site", sa.String(64), primary_key=True),
        sa.Column("identity_type", sa.String(16), primary_key=True),
        sa.Column("identity_key", sa.Text(), primary_key=True),
        sa.Column("authoritative_user_id", sa.BigInteger(), nullable=True),
        sa.Column("observation_id", sa.String(32), nullable=True),
        sa.Column("authority", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="management",
    )


def downgrade():
    op.drop_table("migration_source_identities", schema="management")
