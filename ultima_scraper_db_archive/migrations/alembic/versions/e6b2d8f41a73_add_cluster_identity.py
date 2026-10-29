"""Add management.cluster, the id shared by every backend on this database.

Backends that share a database form one cluster. The id is created here, once
per database, so every backend reads the same value.

Revision ID: e6b2d8f41a73
Revises: c3e9f17a5d48
Create Date: 2026-10-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6b2d8f41a73"
down_revision: Union[str, Sequence[str], None] = "c3e9f17a5d48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the single-row table and its cluster id."""
    op.create_table(
        "cluster",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_cluster_single_row"),
        sa.PrimaryKeyConstraint("id"),
        schema="management",
    )
    op.execute("INSERT INTO management.cluster (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    """Drop the table; backends then report no cluster."""
    op.drop_table("cluster", schema="management")
