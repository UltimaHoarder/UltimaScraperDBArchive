"""Let the transaction-pooled runtime role manage job history partitions.

The application can run as a DML-only role behind PgBouncer transaction
pooling (``usr_runtime``), while the migration owner keeps every table. Three
runtime operations need ownership: attaching a job's history partition,
dropping it, and truncating an empty event partition. These SECURITY DEFINER
functions do exactly those, for validated names only, inside the caller's
transaction (so the existing advisory-lock fences and atomicity are kept).

Each function derives the partition name itself (the same rule as
``job_partitions.partition_name``), accepts only the four history tables,
quotes every identifier and pins ``search_path``. EXECUTE is granted to
``usr_runtime`` when that role exists; the owner can always call them.
"""

from alembic import op

revision = "b7c41e9a2d58"
down_revision = "a4b8e19f23c0"
branch_labels = None
depends_on = None

FUNCTIONS = (
    "management.usr_attach_history_partition(text, text)",
    "management.usr_drop_history_partition(text, text)",
    "management.usr_truncate_outbox_partition(text)",
)

UPGRADE = r"""
CREATE OR REPLACE FUNCTION management.usr_history_partition_name(p_table text, p_run_id text)
RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $$
BEGIN
  IF p_table NOT IN ('execution_mutations', 'execution_attempts', 'execution_outbox', 'job_tasks') THEN
    RAISE EXCEPTION 'Unknown history table %', p_table USING ERRCODE = '22023';
  END IF;
  IF p_run_id IS NULL OR p_run_id = '' THEN
    RAISE EXCEPTION 'A run ID is required' USING ERRCODE = '22023';
  END IF;
  RETURN p_table || '_job_' || left(encode(sha256(convert_to(p_run_id, 'UTF8')), 'hex'), 32);
END $$;

CREATE OR REPLACE FUNCTION management.usr_attach_history_partition(p_table text, p_run_id text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, management, pg_temp AS $$
DECLARE
  leaf text := management.usr_history_partition_name(p_table, p_run_id);
BEGIN
  -- Same statements as job_partitions._ensure_partitions: attach an empty
  -- table, so the parent needs only SHARE UPDATE EXCLUSIVE.
  EXECUTE format(
    'CREATE TABLE management.%I (LIKE management.%I INCLUDING DEFAULTS INCLUDING CONSTRAINTS '
    'INCLUDING GENERATED INCLUDING STORAGE INCLUDING COMMENTS)', leaf, p_table);
  EXECUTE format(
    'ALTER TABLE management.%I ATTACH PARTITION management.%I FOR VALUES IN (%L)',
    p_table, leaf, p_run_id);
END $$;

CREATE OR REPLACE FUNCTION management.usr_drop_history_partition(p_table text, p_run_id text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, management, pg_temp AS $$
DECLARE
  leaf text := management.usr_history_partition_name(p_table, p_run_id);
BEGIN
  -- Only the run's own leaf of that parent, never another relation.
  IF NOT EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
    WHERE c.oid = to_regclass('management.' || quote_ident(leaf))
      AND i.inhparent = to_regclass('management.' || quote_ident(p_table))
      AND pg_get_expr(c.relpartbound, c.oid) = format('FOR VALUES IN (%L)', p_run_id)
  ) THEN
    RETURN false;
  END IF;
  EXECUTE format('DROP TABLE management.%I', leaf);
  RETURN true;
END $$;

CREATE OR REPLACE FUNCTION management.usr_truncate_outbox_partition(p_leaf text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, management, pg_temp AS $$
BEGIN
  IF p_leaf !~ '^execution_outbox_job_[0-9a-f]{32}$' OR NOT EXISTS (
    SELECT 1 FROM pg_inherits
    WHERE inhrelid = to_regclass('management.' || quote_ident(p_leaf))
      AND inhparent = 'management.execution_outbox'::regclass
  ) THEN
    RAISE EXCEPTION 'Not an execution_outbox job partition: %', p_leaf USING ERRCODE = '22023';
  END IF;
  EXECUTE format('TRUNCATE management.%I', p_leaf);
END $$;
"""

GRANTS = """
DO $$
BEGIN
  {revokes}
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'usr_runtime') THEN
    {grants}
  END IF;
END $$;
"""


def _statements(sql: str) -> list[str]:
    # asyncpg (Alembic's driver here) runs one statement per call; each
    # function body ends at its closing "END $$;".
    return [part.strip() + "\n$$" for part in sql.split("$$;") if part.strip()]


def upgrade() -> None:
    for statement in _statements(UPGRADE):
        op.execute(statement)
    op.execute(GRANTS.format(
        revokes=" ".join(f"REVOKE ALL ON FUNCTION {name} FROM PUBLIC;" for name in FUNCTIONS),
        grants=" ".join(f"GRANT EXECUTE ON FUNCTION {name} TO usr_runtime;" for name in FUNCTIONS),
    ))


def downgrade() -> None:
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}")
    op.execute("DROP FUNCTION IF EXISTS management.usr_history_partition_name(text, text)")
