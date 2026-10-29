"""Add frozen MPS retry inputs for resumable definition copying.

Revision ID: e25ac8106df4
Revises: d613ac49e82b
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e25ac8106df4"
down_revision = "d613ac49e82b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mps_retry_tasks",
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("read_bytes", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("ordinal >= 0 AND read_bytes > 0", name="ck_mps_retry_task_bounds"),
        sa.ForeignKeyConstraint(["job_id"], ["management.mps_plans.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "ordinal"),
        schema="management",
    )


def downgrade():
    op.drop_table("mps_retry_tasks", schema="management")
