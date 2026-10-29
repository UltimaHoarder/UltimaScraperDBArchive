"""Partition mutation history; existing runs retain a shared legacy leaf.

Requires a reviewed maintenance window: validation scans legacy history.
No row copying is performed. Upgrade never disposes existing data.
"""

from alembic import op
from sqlalchemy import text

revision = "a84df9201c76"
down_revision = "e761bc24a908"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    # Fail rather than waiting indefinitely behind active execution/deletion.
    db.execute(text("SET LOCAL lock_timeout='5s'"))
    db.execute(
        text(
            "LOCK TABLE management.execution_runs, management.execution_mutations IN ACCESS EXCLUSIVE MODE"
        )
    )
    ids = list(
        db.scalars(text("SELECT run_id FROM management.execution_runs ORDER BY run_id"))
    )
    db.execute(
        text(
            "ALTER TABLE management.execution_mutations RENAME TO execution_mutations_legacy"
        )
    )
    db.execute(
        text(
            "ALTER INDEX management.idx_execution_mutations_command RENAME TO idx_execution_mutations_command_legacy"
        )
    )
    db.execute(
        text("""CREATE TABLE management.execution_mutations (
        run_id varchar(64) NOT NULL REFERENCES management.execution_runs(run_id) ON DELETE CASCADE,
        task_id varchar(64) NOT NULL, mutation_key varchar(128) NOT NULL, command_id varchar(128) NOT NULL,
        CONSTRAINT execution_mutations_partitioned_pkey PRIMARY KEY(run_id,task_id,mutation_key)
    ) PARTITION BY LIST(run_id)""")
    )
    db.execute(
        text(
            "CREATE INDEX idx_execution_mutations_command ON management.execution_mutations(command_id)"
        )
    )
    if ids:
        values = ",".join("'" + value.replace("'", "''") + "'" for value in ids)
        db.execute(
            text(
                "ALTER TABLE management.execution_mutations ATTACH PARTITION management.execution_mutations_legacy FOR VALUES IN ("
                + values
                + ")"
            )
        )
    else:
        # A valid FK implies no rows when there are no runs; still check explicitly.
        if db.scalar(
            text("SELECT EXISTS(SELECT 1 FROM management.execution_mutations_legacy)")
        ):
            raise RuntimeError(
                "Unowned legacy mutations must be reconciled before migration"
            )
        db.execute(text("DROP TABLE management.execution_mutations_legacy"))


def downgrade():
    raise RuntimeError(
        "Partitioned mutation history requires a reviewed flattening migration; refusing destructive automatic downgrade"
    )
