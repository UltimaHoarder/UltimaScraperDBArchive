"""Index bounded ledger claims in their existing oldest-first order."""

from alembic import op

revision = "c7d2e84a19b6"
down_revision = "f6b83a9021c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_execution_work_claim_order",
        "execution_work",
        ["run_id", "created_at", "task_id"],
        schema="management",
        postgresql_where="state = 'queued'",
    )


def downgrade():
    op.drop_index(
        "idx_execution_work_claim_order",
        table_name="execution_work",
        schema="management",
    )
