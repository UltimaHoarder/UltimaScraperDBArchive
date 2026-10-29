"""Durable, indexed MPS selections and rolling execution checkpoints.

Revision ID: a0f7d3c6e921
Revises: 8b3e0d5a2c91
"""

import sqlalchemy as sa
from alembic import op

revision = "a0f7d3c6e921"
down_revision = "8b3e0d5a2c91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mps_plans",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("site", sa.String(64), nullable=False),
        sa.Column("job_config_json", sa.Text(), nullable=False),
        sa.Column("selection_json", sa.Text(), nullable=False),
        sa.Column("proxy_pool_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("cursor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "total >= 0 AND cursor >= 0 AND cursor <= total", name="ck_mps_plan_cursor"
        ),
        schema="management",
    )
    op.create_index(
        "idx_mps_plans_status_job",
        "mps_plans",
        ["status", "job_id"],
        schema="management",
    )
    op.create_table(
        "mps_candidate_ranges",
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("management.mps_plans.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("first_ordinal", sa.BigInteger(), primary_key=True),
        sa.Column("start_id", sa.BigInteger(), nullable=False),
        sa.Column("end_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "first_ordinal >= 0 AND start_id > 0 AND end_id >= start_id",
            name="ck_mps_candidate_range",
        ),
        schema="management",
    )


def downgrade() -> None:
    op.drop_table("mps_candidate_ranges", schema="management")
    op.drop_index(
        "idx_mps_plans_status_job", table_name="mps_plans", schema="management"
    )
    op.drop_table("mps_plans", schema="management")
