"""Durable writer outcomes and failed-command evidence.

Revision ID: bd61e4a92f07
Revises: a0f7d3c6e921
"""

import sqlalchemy as sa
from alembic import op

revision = "bd61e4a92f07"
down_revision = "a0f7d3c6e921"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "database_write_receipts",
        sa.Column("command_id", sa.String(128), primary_key=True),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("site", sa.String(64), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("failed_command_json", sa.Text(), nullable=True),
        sa.Column("post_commit_json", sa.Text(), nullable=True),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="management",
    )


def downgrade() -> None:
    op.drop_table("database_write_receipts", schema="management")
