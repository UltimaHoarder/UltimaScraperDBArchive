"""Retain canonical profile identity independently of task display names.

Revision ID: f14c08a932de
Revises: de82a96c410f
"""

from alembic import op
import sqlalchemy as sa

revision = "f14c08a932de"
down_revision = "de82a96c410f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_tasks",
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        schema="management",
    )


def downgrade():
    op.drop_column("job_tasks", "user_id", schema="management")
