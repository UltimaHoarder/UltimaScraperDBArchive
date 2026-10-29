"""Partition all job history and preserve global identities.

Preserves already partitioned mutation history and partitions remaining history.
Unpartitioned history is rewritten under exclusive locks. Requires a reviewed maintenance
window and sufficient disk/WAL capacity. Does not discard historical rows.
"""

from alembic import op
from sqlalchemy import text
from sqlalchemy.schema import CreateIndex, CreateTable

revision = "c92ea6407b31"
down_revision = "a84df9201c76"
branch_labels = None
depends_on = None


def _literal(value):
    return "'" + value.replace("'", "''") + "'"



def _preserve_partitioned_mutations(db):
    row = db.execute(
        text(
            "SELECT relkind::text, pg_get_partkeydef(oid) FROM pg_class "
            "WHERE oid=to_regclass('management.execution_mutations')"
        )
    ).first()
    if row is None or row[0] != "p":
        return False
    if row[1] != "LIST (run_id)":
        raise RuntimeError("Unexpected mutation partition key; refusing history rewrite")
    # a84df9201c76 already attached existing data without copying it. Runtime
    # provisioning/deletion supports its bounded legacy leaf. Keep its OIDs,
    # indexes and rows intact rather than rewriting millions of legacy records.
    return True


def upgrade():
    import hashlib

    from ultima_scraper_db_archive.execution_models import (
        ExecutionAttemptIdentityModel,
        ExecutionAttemptModel,
        ExecutionMutationModel,
        ExecutionOutboxIdentityModel,
        ExecutionOutboxModel,
        JobTaskIdentityModel,
    )
    from ultima_scraper_db_archive.global_db import CentralTaskModel

    db = op.get_bind()
    db.execute(text("SET LOCAL lock_timeout='5s'"))
    db.execute(
        text(
            "LOCK TABLE management.execution_runs, management.execution_mutations, management.execution_attempts, management.execution_outbox, management.job_tasks IN ACCESS EXCLUSIVE MODE"
        )
    )
    history = [
        ExecutionMutationModel.__table__,
        ExecutionAttemptModel.__table__,
        ExecutionOutboxModel.__table__,
        CentralTaskModel.__table__,
    ]
    directories = [
        ExecutionAttemptIdentityModel.__table__,
        ExecutionOutboxIdentityModel.__table__,
        JobTaskIdentityModel.__table__,
    ]
    for directory in directories:
        directory.create(db, checkfirst=True)
    # Incoming references require a separate reviewed migration, never CASCADE.
    for table in history:
        if table.name == "execution_mutations" and _preserve_partitioned_mutations(db):
            continue
        incoming = db.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE contype='f' AND confrelid=to_regclass(:table))"
            ),
            {"table": "management." + table.name},
        )
        if incoming:
            raise RuntimeError(
                "History table has incoming references; refusing partition conversion: "
                + table.name
            )
        owner = "job_id" if table.name == "job_tasks" else "run_id"
        owners = list(
            db.scalars(
                text(
                    f"SELECT DISTINCT {owner} FROM management.{table.name} ORDER BY {owner}"
                )
            )
        )
        # Include empty retained runs: admission may have already happened.
        owners = sorted(
            set(owners)
            | set(db.scalars(text("SELECT run_id FROM management.execution_runs")))
        )
        # Free deterministic runtime leaf names and index names for replacement.
        leaves = db.execute(
            text(
                "SELECT relid::regclass::text,relid::oid::bigint FROM pg_partition_tree(to_regclass(:table)) WHERE level>0 ORDER BY level DESC"
            ),
            {"table": "management." + table.name},
        ).all()
        for relation, oid in leaves:
            db.exec_driver_sql(f"ALTER TABLE {relation} RENAME TO history_backup_{oid}")
        indexes = db.execute(
            text(
                "SELECT indexrelid::regclass::text,indexrelid::oid::bigint FROM pg_index WHERE indrelid=to_regclass(:table)"
            ),
            {"table": "management." + table.name},
        ).all()
        for relation, oid in indexes:
            db.exec_driver_sql(
                f"ALTER INDEX {relation} RENAME TO history_backup_index_{oid}"
            )
        db.exec_driver_sql(
            f"ALTER TABLE management.{table.name} RENAME TO {table.name}_backup"
        )
        db.execute(CreateTable(table))
        for index in table.indexes:
            db.execute(CreateIndex(index))
        for job_id in owners:
            leaf = (
                table.name + "_job_" + hashlib.sha256(job_id.encode()).hexdigest()[:32]
            )
            db.exec_driver_sql(
                f"CREATE TABLE management.{leaf} PARTITION OF management.{table.name} FOR VALUES IN ({_literal(job_id)})"
            )
        columns = ",".join(
            db.dialect.identifier_preparer.quote(column.name)
            for column in table.columns
        )
        db.exec_driver_sql(
            f"INSERT INTO management.{table.name} ({columns}) SELECT {columns} FROM management.{table.name}_backup"
        )
        if table.name == "execution_outbox":
            db.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('management.execution_outbox','event_id'),GREATEST(COALESCE((SELECT max(event_id) FROM management.execution_outbox),1),1),EXISTS(SELECT 1 FROM management.execution_outbox))"
                )
            )
        db.exec_driver_sql(f"DROP TABLE management.{table.name}_backup")
    db.execute(
        text(
            "INSERT INTO management.execution_attempt_identities SELECT token,run_id,task_id,number FROM management.execution_attempts"
        )
    )
    db.execute(
        text(
            "INSERT INTO management.execution_outbox_identities SELECT event_id,run_id,sequence FROM management.execution_outbox"
        )
    )
    db.execute(
        text(
            "INSERT INTO management.job_task_identities SELECT task_id,job_id FROM management.job_tasks"
        )
    )
    db.execute(text("""CREATE FUNCTION management.history_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME LIKE 'execution_attempts%' THEN
        IF TG_OP='DELETE' THEN
          DELETE FROM management.execution_attempt_identities WHERE token=OLD.token AND run_id=OLD.run_id; RETURN OLD;
        END IF;
        INSERT INTO management.execution_attempt_identities VALUES(NEW.token,NEW.run_id,NEW.task_id,NEW.number) ON CONFLICT(token) DO NOTHING;
        IF NOT EXISTS(SELECT 1 FROM management.execution_attempt_identities WHERE token=NEW.token AND run_id=NEW.run_id AND task_id=NEW.task_id AND number=NEW.number) THEN
          RAISE EXCEPTION 'Attempt token already belongs to another attempt' USING ERRCODE='23505';
        END IF;
        IF TG_OP='UPDATE' AND OLD.token IS DISTINCT FROM NEW.token THEN
          DELETE FROM management.execution_attempt_identities WHERE token=OLD.token AND run_id=OLD.run_id;
        END IF;
      ELSIF TG_TABLE_NAME LIKE 'execution_outbox%' THEN
        IF TG_OP='DELETE' THEN
          DELETE FROM management.execution_outbox_identities WHERE event_id=OLD.event_id AND run_id=OLD.run_id; RETURN OLD;
        END IF;
        INSERT INTO management.execution_outbox_identities VALUES(NEW.event_id,NEW.run_id,NEW.sequence)
          ON CONFLICT(event_id) DO UPDATE SET sequence=excluded.sequence WHERE execution_outbox_identities.run_id=excluded.run_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Event ID already belongs to another job' USING ERRCODE='23505'; END IF;
        IF TG_OP='UPDATE' AND (OLD.event_id IS DISTINCT FROM NEW.event_id OR OLD.run_id IS DISTINCT FROM NEW.run_id) THEN
          RAISE EXCEPTION 'Event identity is immutable' USING ERRCODE='23505';
        END IF;
      ELSE
        IF TG_OP='DELETE' THEN
          DELETE FROM management.job_task_identities WHERE task_id=OLD.task_id AND job_id=OLD.job_id; RETURN OLD;
        END IF;
        INSERT INTO management.job_task_identities VALUES(NEW.task_id,NEW.job_id) ON CONFLICT(task_id) DO NOTHING;
        IF NOT EXISTS(SELECT 1 FROM management.job_task_identities WHERE task_id=NEW.task_id AND job_id=NEW.job_id) THEN
          RAISE EXCEPTION 'Task ID already belongs to another job' USING ERRCODE='23505';
        END IF;
        IF TG_OP='UPDATE' AND (OLD.task_id IS DISTINCT FROM NEW.task_id OR OLD.job_id IS DISTINCT FROM NEW.job_id) THEN
          RAISE EXCEPTION 'Task identity is immutable' USING ERRCODE='23505';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""))
    for table in ("execution_attempts", "execution_outbox", "job_tasks"):
        db.exec_driver_sql(
            f"CREATE TRIGGER history_identity_guard BEFORE INSERT OR UPDATE OR DELETE ON management.{table} FOR EACH ROW EXECUTE FUNCTION management.history_identity_guard()"
        )


def downgrade():
    raise RuntimeError(
        "History repartitioning requires a reviewed reverse migration; refusing automatic destructive downgrade"
    )
