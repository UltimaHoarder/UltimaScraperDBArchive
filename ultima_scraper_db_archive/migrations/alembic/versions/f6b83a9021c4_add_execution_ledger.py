"""Add versioned job runs, fenced attempts and a transactional event outbox."""

from alembic import op

revision = "f6b83a9021c4"
down_revision = "e3f1a2b4c5d6"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "CREATE TABLE management.execution_definitions (\n\tdefinition_id VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tconfig_json TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (definition_id, revision)\n)",
    "CREATE TABLE management.execution_runs (\n\trun_id VARCHAR(64) NOT NULL, \n\tdefinition_id VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstate VARCHAR(16) DEFAULT 'pending' NOT NULL, \n\tbackend_id VARCHAR(64), \n\tpriority INTEGER DEFAULT '0' NOT NULL, \n\tconfig_json TEXT NOT NULL, \n\tnext_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tlast_admitted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (run_id), \n\tFOREIGN KEY(definition_id, revision) REFERENCES management.execution_definitions (definition_id, revision), \n\tCONSTRAINT ck_execution_run_state CHECK (state IN ('pending','running','paused','completed','failed','cancelled'))\n)",
    "CREATE TABLE management.execution_work (\n\trun_id VARCHAR(64) NOT NULL, \n\ttask_id VARCHAR(64) NOT NULL, \n\tstate VARCHAR(16) DEFAULT 'queued' NOT NULL, \n\tlane VARCHAR(16) NOT NULL, \n\tsite VARCHAR(64) NOT NULL, \n\tcapabilities TEXT[] NOT NULL, \n\tdedup_key TEXT NOT NULL, \n\tpayload_json TEXT NOT NULL, \n\tpayload_bytes BIGINT NOT NULL, \n\tcandidate BIGINT, \n\tattempt INTEGER DEFAULT '0' NOT NULL, \n\ttoken VARCHAR(64), \n\towner VARCHAR(64), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tavailable_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (run_id, task_id), \n\tCONSTRAINT ck_execution_work_state CHECK (state IN ('queued','running','persisting','completed','failed','cancelled')), \n\tCONSTRAINT ck_execution_work_budget CHECK (payload_bytes >= 0 AND attempt >= 0), \n\tFOREIGN KEY(run_id) REFERENCES management.execution_runs (run_id) ON DELETE CASCADE\n)",
    "CREATE TABLE management.execution_attempts (\n\trun_id VARCHAR(64) NOT NULL, \n\ttask_id VARCHAR(64) NOT NULL, \n\tnumber INTEGER NOT NULL, \n\ttoken VARCHAR(64) NOT NULL, \n\towner VARCHAR(64) NOT NULL, \n\tstate VARCHAR(16) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\terror TEXT, \n\ttimings_json TEXT DEFAULT '{}' NOT NULL, \n\tPRIMARY KEY (run_id, task_id, number), \n\tCONSTRAINT uq_execution_attempt_token UNIQUE (token), \n\tFOREIGN KEY(run_id) REFERENCES management.execution_runs (run_id) ON DELETE CASCADE\n)",
    "CREATE TABLE management.execution_resources (\n\tresource_key TEXT NOT NULL, \n\ttoken VARCHAR(64) NOT NULL, \n\trun_id VARCHAR(64) NOT NULL, \n\ttask_id VARCHAR(64) NOT NULL, \n\tlease_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (resource_key), \n\tFOREIGN KEY(run_id) REFERENCES management.execution_runs (run_id) ON DELETE CASCADE\n)",
    "CREATE TABLE management.execution_outbox (\n\tevent_id BIGSERIAL NOT NULL, \n\trun_id VARCHAR(64) NOT NULL, \n\tpayload_json TEXT NOT NULL, \n\tsequence BIGINT, \n\tdelivered BOOLEAN DEFAULT 'false' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (event_id), \n\tCONSTRAINT uq_execution_outbox_sequence UNIQUE (sequence), \n\tFOREIGN KEY(run_id) REFERENCES management.execution_runs (run_id) ON DELETE CASCADE\n)",
    "CREATE TABLE management.execution_mutations (\n\trun_id VARCHAR(64) NOT NULL, \n\ttask_id VARCHAR(64) NOT NULL, \n\tmutation_key VARCHAR(128) NOT NULL, \n\tcommand_id VARCHAR(128) NOT NULL, \n\tPRIMARY KEY (run_id, task_id, mutation_key), \n\tFOREIGN KEY(run_id) REFERENCES management.execution_runs (run_id) ON DELETE CASCADE\n)",
    "CREATE TABLE management.execution_feed (\n\tfeed_id SERIAL NOT NULL, \n\tnext_sequence BIGINT DEFAULT '1' NOT NULL, \n\tPRIMARY KEY (feed_id)\n)",
    "CREATE INDEX idx_execution_runs_active ON management.execution_runs (state, next_at, last_admitted_at)",
    "CREATE INDEX idx_execution_work_expired ON management.execution_work (lease_until) WHERE state IN ('running','persisting')",
    "CREATE INDEX idx_execution_work_ready ON management.execution_work (lane, available_at, run_id) WHERE state = 'queued'",
    "CREATE INDEX idx_execution_attempts_run ON management.execution_attempts (run_id, started_at)",
    "CREATE INDEX idx_execution_outbox_pending ON management.execution_outbox (event_id) WHERE delivered = false",
    "INSERT INTO management.execution_feed (feed_id) VALUES (1)",
)

DOWNGRADE_SQL = (
    "DROP TABLE management.execution_feed",
    "DROP TABLE management.execution_mutations",
    "DROP TABLE management.execution_outbox",
    "DROP TABLE management.execution_resources",
    "DROP TABLE management.execution_attempts",
    "DROP TABLE management.execution_work",
    "DROP TABLE management.execution_runs",
    "DROP TABLE management.execution_definitions",
)


def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade():
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
