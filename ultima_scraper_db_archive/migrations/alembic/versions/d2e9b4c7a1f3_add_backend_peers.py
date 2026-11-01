"""Add backend peer tokens.

Each backend gets its own token for calling other backends on the same
database, such as handing a download to the backend that stores it. Only the
token's hash is stored; revoking one backend leaves the others working.

Revision ID: d2e9b4c7a1f3
Revises: c7b3857c294c
Create Date: 2026-11-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e9b4c7a1f3"
down_revision: Union[str, Sequence[str], None] = "c7b3857c294c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create one peer token row per backend."""
    op.create_table(
        "backend_peers",
        sa.Column("backend_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("backend_id"),
        schema="management",
    )
    op.create_index(
        "idx_backend_peers_token_hash",
        "backend_peers",
        ["token_hash"],
        unique=True,
        schema="management",
    )


def downgrade() -> None:
    """Drop the peer tokens."""
    op.drop_index("idx_backend_peers_token_hash", table_name="backend_peers", schema="management")
    op.drop_table("backend_peers", schema="management")
