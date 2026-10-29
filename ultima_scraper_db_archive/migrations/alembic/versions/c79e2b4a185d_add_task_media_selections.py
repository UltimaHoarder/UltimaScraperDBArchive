"""Add durable, pageable media selections and task evidence.

Revision ID: c79e2b4a185d
Revises: bd61e4a92f07
"""

from alembic import op
import sqlalchemy as sa

revision = "c79e2b4a185d"
down_revision = "bd61e4a92f07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_media_plans",
        sa.Column("selection_id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("site", sa.String(64), nullable=False),
        sa.Column("auth_id", sa.BigInteger(), nullable=True),
        sa.Column("ready", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("total", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="management",
    )
    op.create_table(
        "task_media_selections",
        sa.Column(
            "selection_id",
            sa.String(64),
            sa.ForeignKey(
                "management.task_media_plans.selection_id", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_type", sa.String(32), primary_key=True),
        sa.Column("media_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("content_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("drm_json", sa.Text(), nullable=True),
        schema="management",
    )
    op.create_table(
        "task_media_evidence",
        sa.Column(
            "selection_id",
            sa.String(64),
            sa.ForeignKey(
                "management.task_media_plans.selection_id", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("ordinal", sa.BigInteger(), primary_key=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        schema="management",
    )


def downgrade():
    op.drop_table("task_media_evidence", schema="management")
    op.drop_table("task_media_selections", schema="management")
    op.drop_table("task_media_plans", schema="management")
