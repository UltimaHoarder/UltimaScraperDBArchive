"""Index restartable, per-job database write receipt deletion.

Revision ID: 6f4b2e9a17c0
Revises: 35a2cb48418e

Concurrent construction preserves writer access. A failed build can be retried;
the narrower old index is removed only after its replacement is valid.
"""

from alembic import op
import sqlalchemy as sa

revision = "6f4b2e9a17c0"
down_revision = "35a2cb48418e"
branch_labels = None
depends_on = None


def _index(name, columns):
    valid = op.get_bind().scalar(sa.text(
        "SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)"
    ), {"name": "management." + name})
    if valid is False:
        op.execute("DROP INDEX CONCURRENTLY management." + name)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS " + name
               + " ON management.database_write_receipts " + columns
               + " WHERE run_id IS NOT NULL")


def upgrade():
    with op.get_context().autocommit_block():
        _index("idx_write_receipts_run_command", "(run_id, command_id)")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_write_receipts_run")


def downgrade():
    with op.get_context().autocommit_block():
        _index("idx_write_receipts_run", "(run_id)")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS management.idx_write_receipts_run_command")
