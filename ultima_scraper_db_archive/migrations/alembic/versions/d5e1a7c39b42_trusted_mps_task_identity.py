"""Let the MPS archiver skip the global task directory for proven task IDs.

MPS candidate task IDs are uuid5 values of their job, ordinal and user. The
archiver verifies each one before inserting it into job history and sets the
transaction-local ``ultima.trusted_mps_identity`` flag only for those rows.
Without the flag (every other writer, and the default), the guard is unchanged.
DELETE and UPDATE keep full enforcement.
"""

from alembic import op

revision = "d5e1a7c39b42"
down_revision = "a43f7c9d2e61"
branch_labels = None
depends_on = None

PREVIOUS_GUARD = """CREATE OR REPLACE FUNCTION management.history_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME LIKE 'execution_attempts%' THEN
        IF TG_OP='DELETE' THEN
          DELETE FROM management.execution_attempt_identities WHERE token=OLD.token AND run_id=OLD.run_id; RETURN OLD;
        END IF;
        INSERT INTO management.execution_attempt_identities VALUES(NEW.token,NEW.run_id,NEW.task_id,NEW.number) ON CONFLICT(token) DO NOTHING;
        IF NOT FOUND THEN
          IF NOT EXISTS(SELECT 1 FROM management.execution_attempt_identities WHERE token=NEW.token AND run_id=NEW.run_id AND task_id=NEW.task_id AND number=NEW.number) THEN
            RAISE EXCEPTION 'Attempt token already belongs to another attempt' USING ERRCODE='23505';
          END IF;
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
        IF NOT FOUND THEN
          IF NOT EXISTS(SELECT 1 FROM management.job_task_identities WHERE task_id=NEW.task_id AND job_id=NEW.job_id) THEN
            RAISE EXCEPTION 'Task ID already belongs to another job' USING ERRCODE='23505';
          END IF;
        END IF;
        IF TG_OP='UPDATE' AND (OLD.task_id IS DISTINCT FROM NEW.task_id OR OLD.job_id IS DISTINCT FROM NEW.job_id) THEN
          RAISE EXCEPTION 'Task identity is immutable' USING ERRCODE='23505';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""

TRUSTED_GUARD = """CREATE OR REPLACE FUNCTION management.history_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME LIKE 'execution_attempts%' THEN
        IF TG_OP='DELETE' THEN
          DELETE FROM management.execution_attempt_identities WHERE token=OLD.token AND run_id=OLD.run_id; RETURN OLD;
        END IF;
        INSERT INTO management.execution_attempt_identities VALUES(NEW.token,NEW.run_id,NEW.task_id,NEW.number) ON CONFLICT(token) DO NOTHING;
        IF NOT FOUND THEN
          IF NOT EXISTS(SELECT 1 FROM management.execution_attempt_identities WHERE token=NEW.token AND run_id=NEW.run_id AND task_id=NEW.task_id AND number=NEW.number) THEN
            RAISE EXCEPTION 'Attempt token already belongs to another attempt' USING ERRCODE='23505';
          END IF;
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
        -- The MPS archiver proved this row's ID derives from its own job
        -- (uuid5 of job, ordinal and user) and set this LOCAL flag for it.
        IF TG_OP='INSERT' AND current_setting('ultima.trusted_mps_identity', true) = 'on' THEN
          RETURN NEW;
        END IF;
        INSERT INTO management.job_task_identities VALUES(NEW.task_id,NEW.job_id) ON CONFLICT(task_id) DO NOTHING;
        IF NOT FOUND THEN
          IF NOT EXISTS(SELECT 1 FROM management.job_task_identities WHERE task_id=NEW.task_id AND job_id=NEW.job_id) THEN
            RAISE EXCEPTION 'Task ID already belongs to another job' USING ERRCODE='23505';
          END IF;
        END IF;
        IF TG_OP='UPDATE' AND (OLD.task_id IS DISTINCT FROM NEW.task_id OR OLD.job_id IS DISTINCT FROM NEW.job_id) THEN
          RAISE EXCEPTION 'Task identity is immutable' USING ERRCODE='23505';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""


def upgrade():
    op.execute(TRUSTED_GUARD)


def downgrade():
    op.execute(PREVIOUS_GUARD)
