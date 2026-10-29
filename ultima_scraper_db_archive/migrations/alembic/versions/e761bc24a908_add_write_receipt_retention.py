"""Preserve receipt ownership and index bounded retention checks."""
from alembic import op
import sqlalchemy as sa

revision = "e761bc24a908"
down_revision = "b8f203de9147"
branch_labels = None
depends_on = None


def _index(name, definition):
    # Concurrent builds can leave an invalid index after interruption. Resume
    # must rebuild it rather than accepting IF NOT EXISTS as success.
    valid = op.get_bind().scalar(sa.text(
        "SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)"
    ), {"name": "management." + name})
    if valid is False:
        op.execute("DROP INDEX CONCURRENTLY management." + name)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS " + name + " " + definition)


def upgrade():
    # The column is committed before concurrent builds; tolerate interrupted
    # upgrades which have not yet advanced the Alembic version.
    op.execute("ALTER TABLE management.database_write_receipts ADD COLUMN IF NOT EXISTS run_id varchar(64)")
    with op.get_context().autocommit_block():
        _index("idx_execution_mutations_command", "ON management.execution_mutations (command_id)")
        _index("idx_write_receipts_age", "ON management.database_write_receipts USING brin (committed_at)")
        _index("idx_write_receipts_run", "ON management.database_write_receipts (run_id) WHERE run_id IS NOT NULL")


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_write_receipts_run")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_write_receipts_age")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_execution_mutations_command")
    op.drop_column("database_write_receipts", "run_id", schema="management")
