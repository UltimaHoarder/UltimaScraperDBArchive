"""Add cluster names, clients and invites.

A client (a WebUI) joins a cluster with a one-time invite code and gets its own
token; every backend on this database accepts it until it is revoked. Only
hashes of codes and tokens are stored.

Revision ID: a4c1e7d93b20
Revises: bfd28f1b62e7
Create Date: 2026-10-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c1e7d93b20"
down_revision: Union[str, Sequence[str], None] = "bfd28f1b62e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Name the cluster, and create its clients and invites."""
    op.add_column("cluster", sa.Column("name", sa.Text(), nullable=True), schema="management")
    op.create_table(
        "cluster_clients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="webui", nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_address", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="management",
    )
    op.create_index(
        "idx_cluster_clients_token_hash",
        "cluster_clients",
        ["token_hash"],
        unique=True,
        schema="management",
    )
    op.create_table(
        "cluster_invites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("used_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["used_by"], ["management.cluster_clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="management",
    )
    op.create_index(
        "idx_cluster_invites_code_hash",
        "cluster_invites",
        ["code_hash"],
        unique=True,
        schema="management",
    )


def downgrade() -> None:
    """Drop invites and clients, then the name."""
    op.drop_index("idx_cluster_invites_code_hash", table_name="cluster_invites", schema="management")
    op.drop_table("cluster_invites", schema="management")
    op.drop_index("idx_cluster_clients_token_hash", table_name="cluster_clients", schema="management")
    op.drop_table("cluster_clients", schema="management")
    op.drop_column("cluster", "name", schema="management")
