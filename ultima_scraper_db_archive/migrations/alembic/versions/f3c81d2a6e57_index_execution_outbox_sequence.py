"""Index execution outbox events by global sequence for event replay."""
from alembic import op
from sqlalchemy import text

revision = "f3c81d2a6e57"
down_revision = "e9a62c7138bf"
branch_labels = None
depends_on = None

PARENT_INDEX = "idx_execution_outbox_sequence"


def _leaves(bind):
    return bind.execute(text("""SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
        WHERE i.inhparent='management.execution_outbox'::regclass ORDER BY c.relname""")).scalars().all()


def _attached(bind, leaf_index):
    return bool(bind.scalar(text("""SELECT EXISTS(SELECT 1 FROM pg_inherits
        WHERE inhparent=to_regclass(:parent) AND inhrelid=to_regclass(:leaf))"""),
        {"parent": f"management.{PARENT_INDEX}", "leaf": f"management.{leaf_index}"}))


def upgrade():
    bind = op.get_bind()
    partitioned = bind.scalar(text(
        "SELECT relkind='p' FROM pg_class WHERE oid=to_regclass('management.execution_outbox')"))
    # Existing history must stay writable while each table is indexed.
    with op.get_context().autocommit_block():
        if not partitioned:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {PARENT_INDEX} "
                       "ON management.execution_outbox (sequence)")
            return
        # The parent index starts invalid; partitions attached later (one per
        # job) receive it automatically. Index each existing leaf without
        # blocking writes, then attach it so the parent becomes valid.
        op.execute(f"CREATE INDEX IF NOT EXISTS {PARENT_INDEX} ON ONLY management.execution_outbox (sequence)")
        for leaf in _leaves(bind):
            leaf_index = f"{leaf}_seq"  # within the 63-character name limit
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {leaf_index} ON management.{leaf} (sequence)")
            if not _attached(bind, leaf_index):
                op.execute(f"ALTER INDEX management.{PARENT_INDEX} ATTACH PARTITION management.{leaf_index}")


def downgrade():
    # Dropping the parent index drops every attached leaf index.
    op.execute(f"DROP INDEX IF EXISTS management.{PARENT_INDEX}")
