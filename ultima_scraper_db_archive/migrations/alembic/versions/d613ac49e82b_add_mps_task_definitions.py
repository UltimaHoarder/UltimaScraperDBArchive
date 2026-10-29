"""Durable explicit task definitions for MPS job replacement.

Revision ID: d613ac49e82b
Revises: a92e10b6f3d8
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "d613ac49e82b"
down_revision = "a92e10b6f3d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mps_plans", sa.Column(
        "parent_job_id", sa.String(64), sa.ForeignKey(
            "management.mps_plans.job_id", name="fk_mps_plan_parent", ondelete="CASCADE"
        ), nullable=True,
    ), schema="management")
    op.create_index("idx_mps_plans_parent_job", "mps_plans", ["parent_job_id"], schema="management")
    op.create_table(
        "mps_task_definitions",
        sa.Column(
            "manifest_id", sa.String(64),
            sa.ForeignKey("management.mps_plans.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ordinal", sa.BigInteger(), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("task_json", sa.Text(), nullable=False),
        sa.Column("dependency_ids", ARRAY(sa.String(64)), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.CheckConstraint("ordinal >= 0", name="ck_mps_task_definition_ordinal"),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_mps_task_definition_status",
        ),
        sa.UniqueConstraint("manifest_id", "task_id", name="uq_mps_definition_task"),
        schema="management",
    )
    op.create_index(
        "idx_mps_definition_pending", "mps_task_definitions",
        ["manifest_id", "ordinal"], schema="management",
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("mps_task_definitions", schema="management")
    op.drop_index("idx_mps_plans_parent_job", table_name="mps_plans", schema="management")
    op.drop_constraint("fk_mps_plan_parent", "mps_plans", type_="foreignkey", schema="management")
    op.drop_column("mps_plans", "parent_job_id", schema="management")
