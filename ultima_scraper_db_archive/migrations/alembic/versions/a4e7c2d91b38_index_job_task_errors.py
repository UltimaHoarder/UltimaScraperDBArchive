"""Index failed job tasks so per-job error summaries skip successful rows."""
from alembic import op
from sqlalchemy import text

revision = "a4e7c2d91b38"
down_revision = "ce84a19f027b"  # after the unified favourites migration
branch_labels = None
depends_on = None

PARENT_INDEX = "idx_job_tasks_job_errors"
COLUMNS = "(job_id, error) WHERE error IS NOT NULL"


def upgrade():
    bind = op.get_bind()
    partitioned = bind.scalar(text(
        "SELECT relkind='p' FROM pg_class WHERE oid=to_regclass('management.job_tasks')"))
    # History stays writable while each table is indexed.
    with op.get_context().autocommit_block():
        if not partitioned:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {PARENT_INDEX} ON management.job_tasks {COLUMNS}")
            return
        # Invalid until every leaf attaches; partitions attached later get it.
        op.execute(f"CREATE INDEX IF NOT EXISTS {PARENT_INDEX} ON ONLY management.job_tasks {COLUMNS}")
        leaves = bind.execute(text("""SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
            WHERE i.inhparent='management.job_tasks'::regclass ORDER BY c.relname""")).scalars().all()
        for leaf in leaves:
            leaf_index = f"{leaf}_err"  # within the 63-character name limit
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {leaf_index} ON management.{leaf} {COLUMNS}")
            attached = bind.scalar(text("""SELECT EXISTS(SELECT 1 FROM pg_inherits
                WHERE inhparent=to_regclass(:parent) AND inhrelid=to_regclass(:leaf))"""),
                {"parent": f"management.{PARENT_INDEX}", "leaf": f"management.{leaf_index}"})
            if not attached:
                op.execute(f"ALTER INDEX management.{PARENT_INDEX} ATTACH PARTITION management.{leaf_index}")


def downgrade():
    op.execute(f"DROP INDEX IF EXISTS management.{PARENT_INDEX}")
