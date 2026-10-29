"""Let the runtime role truncate a finished run's history leaves.

History compaction rewrites a run's ``job_tasks`` and ``execution_attempts``
leaves to their kept rows with TRUNCATE, which needs the table owner. Like the
functions of b7c41e9a2d58, this SECURITY DEFINER function does only that, for
the run's own two leaves, inside the caller's transaction, so the compaction's
advisory-lock fence, lock timeout and rollback behave as before.

The leaf names come from ``usr_history_partition_name``, and each leaf must be
attached to its parent for exactly that run. EXECUTE is granted to
``usr_runtime`` when that role exists; the owner can always call it.

Revision ID: c8a3e5f71d26
Revises: a4c1e7d93b20
Create Date: 2026-10-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c8a3e5f71d26"
down_revision: Union[str, Sequence[str], None] = "a4c1e7d93b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTION = "management.usr_truncate_history_partitions(text)"

UPGRADE = r"""
CREATE OR REPLACE FUNCTION management.usr_truncate_history_partitions(p_run_id text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, management, pg_temp AS $$
DECLARE
  attempts_leaf text := management.usr_history_partition_name('execution_attempts', p_run_id);
  tasks_leaf text := management.usr_history_partition_name('job_tasks', p_run_id);
BEGIN
  -- Only the run's own leaves of those parents, never another relation.
  IF (
    SELECT count(*) FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
    WHERE (c.oid, i.inhparent) IN (
        (to_regclass('management.' || quote_ident(attempts_leaf)), 'management.execution_attempts'::regclass),
        (to_regclass('management.' || quote_ident(tasks_leaf)), 'management.job_tasks'::regclass))
      AND pg_get_expr(c.relpartbound, c.oid) = format('FOR VALUES IN (%L)', p_run_id)
  ) <> 2 THEN
    RAISE EXCEPTION 'Run % does not own its history partitions', p_run_id USING ERRCODE = '22023';
  END IF;
  -- Same statement as history_compaction._compact_run.
  EXECUTE format('TRUNCATE management.%I, management.%I', attempts_leaf, tasks_leaf);
END $$;
"""

GRANTS = f"""
DO $$
BEGIN
  REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'usr_runtime') THEN
    GRANT EXECUTE ON FUNCTION {FUNCTION} TO usr_runtime;
  END IF;
END $$;
"""


def upgrade() -> None:
    # asyncpg runs one statement per call.
    op.execute(UPGRADE.strip())
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}")
