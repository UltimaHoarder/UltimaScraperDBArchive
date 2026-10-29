"""Separate bounded work payloads from frequently updated lease/queue rows.

Stop the application before upgrading or downgrading: the old payload column
and its replacement cannot be used by mixed application versions. Existing
heap/index bloat requires a separate reviewed compaction after migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "9e7c3a1d6b20"
down_revision = "6f4b2e9a17c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "execution_work_payloads",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["management.execution_work.run_id", "management.execution_work.task_id"],
            ondelete="CASCADE",
        ),
        schema="management",
    )
    op.execute(
        "ALTER TABLE management.execution_work_payloads SET ("
        "vacuum_index_cleanup=on, autovacuum_vacuum_scale_factor=0, "
        "autovacuum_vacuum_threshold=5000, autovacuum_analyze_scale_factor=0, "
        "autovacuum_analyze_threshold=5000, autovacuum_vacuum_cost_delay=0)"
    )
    op.add_column(
        "execution_work",
        sa.Column("payload_size", sa.BigInteger()),
        schema="management",
    )
    op.execute(
        "INSERT INTO management.execution_work_payloads (run_id,task_id,payload_json) "
        "SELECT run_id,task_id,payload_json FROM management.execution_work"
    )
    op.execute(
        "UPDATE management.execution_work SET payload_size=octet_length(payload_json)"
    )
    op.alter_column(
        "execution_work", "payload_size", nullable=False, schema="management"
    )
    op.drop_column("execution_work", "payload_json", schema="management")
    op.execute("ALTER TABLE management.execution_work SET (fillfactor=70)")
    op.create_index(
        "idx_execution_work_terminal",
        "execution_work",
        ["run_id", "task_id"],
        schema="management",
        postgresql_where=sa.text("state IN ('completed','failed')"),
        postgresql_include=["payload_size"],
    )


def downgrade():
    op.add_column(
        "execution_work", sa.Column("payload_json", sa.Text()), schema="management"
    )
    op.execute(
        "UPDATE management.execution_work w SET payload_json=p.payload_json "
        "FROM management.execution_work_payloads p WHERE p.run_id=w.run_id AND p.task_id=w.task_id"
    )
    op.alter_column(
        "execution_work", "payload_json", nullable=False, schema="management"
    )
    op.drop_index(
        "idx_execution_work_terminal", table_name="execution_work", schema="management"
    )
    op.drop_table("execution_work_payloads", schema="management")
    op.drop_column("execution_work", "payload_size", schema="management")
    op.execute("ALTER TABLE management.execution_work RESET (fillfactor)")
