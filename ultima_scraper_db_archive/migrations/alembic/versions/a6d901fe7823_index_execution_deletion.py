"""Index execution history cleanup and foreign-key cascades."""
from alembic import op

revision = "a6d901fe7823"
down_revision = "c7d2e84a19b6"
branch_labels = None
depends_on = None


def upgrade():
    # Large existing history tables must remain writable during index creation.
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_execution_outbox_run ON management.execution_outbox (run_id, event_id)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_execution_resources_run ON management.execution_resources (run_id)")


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_execution_resources_run")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_execution_outbox_run")
