"""Keep the execution queue compact and stop JIT-compiling short OLTP queries.

execution_work churns hundreds of inserts and deletes per second while holding
only a few thousand live rows. With default autovacuum it skipped index
cleanup and grew to 1.7 GB for ~3k rows, slowing every claim, refill and
archive pass and inflating plan costs past jit_above_cost, so sub-millisecond
queries paid milliseconds of JIT compilation.
"""
from alembic import op

revision = "c5f2a8e17d49"
down_revision = "a4e7c2d91b38"
branch_labels = None
depends_on = None

QUEUE_SETTINGS = (
    "vacuum_index_cleanup = on, "
    "autovacuum_vacuum_scale_factor = 0, autovacuum_vacuum_threshold = 5000, "
    "autovacuum_vacuum_insert_scale_factor = 0, autovacuum_vacuum_insert_threshold = 5000, "
    "autovacuum_analyze_scale_factor = 0, autovacuum_analyze_threshold = 5000, "
    "autovacuum_vacuum_cost_delay = 0"
)


def upgrade():
    op.execute(f"ALTER TABLE management.execution_work SET ({QUEUE_SETTINGS})")
    op.execute("DO $$ BEGIN EXECUTE format('ALTER DATABASE %I SET jit = off', current_database()); END $$")


def downgrade():
    op.execute(
        "ALTER TABLE management.execution_work RESET (vacuum_index_cleanup, "
        "autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold, "
        "autovacuum_vacuum_insert_scale_factor, autovacuum_vacuum_insert_threshold, "
        "autovacuum_analyze_scale_factor, autovacuum_analyze_threshold, autovacuum_vacuum_cost_delay)"
    )
    op.execute("DO $$ BEGIN EXECUTE format('ALTER DATABASE %I RESET jit', current_database()); END $$")
