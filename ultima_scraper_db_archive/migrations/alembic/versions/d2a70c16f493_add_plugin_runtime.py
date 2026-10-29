"""Add PostgreSQL plugin authority and durable deliveries."""

from alembic import op
from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)

revision = "d2a70c16f493"
down_revision = "b8f203de9147"
branch_labels = None
depends_on = None

metadata = MetaData()

plugin_api_tokens = Table(
    "plugin_api_tokens",
    metadata,
    Column("token_hash", Text, primary_key=True),
    Column("plugin_id", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    schema="management",
)

plugin_callback_registrations = Table(
    "plugin_callback_registrations",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_capability_grant_sets = Table(
    "plugin_capability_grant_sets",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("approved_at", Text, nullable=False),
    schema="management",
)

plugin_capability_grants = Table(
    "plugin_capability_grants",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("capability", Text, primary_key=True),
    Column("granted_at", Text, nullable=False),
    schema="management",
)

plugin_configuration = Table(
    "plugin_configuration",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_delivery_attempts = Table(
    "plugin_delivery_attempts",
    metadata,
    Column("delivery_id", Text, primary_key=True),
    Column("plugin_id", Text, nullable=False),
    Column("target_name", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("next_retry_at", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_delivery_queue = Table(
    "plugin_delivery_queue",
    metadata,
    Column("delivery_id", Text, primary_key=True),
    Column("plugin_id", Text, nullable=False),
    Column("target_name", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("manifest_json", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("available_at", Text, nullable=False),
    Column("lease_token", Text, nullable=True),
    Column("lease_until", Text, nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("plugin_id", "target_name", "event_id"),
    schema="management",
)

plugin_event_cursors = Table(
    "plugin_event_cursors",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("sequence", BigInteger, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_installations = Table(
    "plugin_installations",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("enabled", Integer, nullable=False, server_default="0"),
    Column("missing_since", Text, nullable=True),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_packages = Table(
    "plugin_packages",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("digest", Text, primary_key=True),
    Column("plugin_version", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    schema="management",
)

plugin_quotas = Table(
    "plugin_quotas",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("quota_bytes", Integer, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_repository_meta = Table(
    "plugin_repository_meta",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
    schema="management",
)

plugin_runtime_correlations = Table(
    "plugin_runtime_correlations",
    metadata,
    Column("correlation_id", Text, primary_key=True),
    Column("plugin_id", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_runtime_leases = Table(
    "plugin_runtime_leases",
    metadata,
    Column("resource_key", Text, primary_key=True),
    Column("owner_id", Text, nullable=False),
    Column("lease_token", Text, nullable=False),
    Column("lease_until", Text, nullable=False),
    schema="management",
)

plugin_runtime_owner = Table(
    "plugin_runtime_owner",
    metadata,
    Column("singleton", Integer, primary_key=True),
    Column("owner_id", Text, nullable=False),
    Column("pid", Integer, nullable=False),
    Column("started_at", Text, nullable=False),
    Column("heartbeat_at", Text, nullable=False),
    schema="management",
)

plugin_scope_grants = Table(
    "plugin_scope_grants",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_secrets = Table(
    "plugin_secrets",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("scope_kind", Text, primary_key=True),
    Column("scope_name", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_state = Table(
    "plugin_state",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("state_key", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

plugin_state_audit = Table(
    "plugin_state_audit",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("plugin_id", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    schema="management",
)

plugin_websocket_sessions = Table(
    "plugin_websocket_sessions",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("payload_json", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

Index(
    "ix_plugin_state_audit_plugin_id_id",
    plugin_state_audit.c.plugin_id,
    plugin_state_audit.c.id,
)
Index(
    "ix_plugin_runtime_correlations_plugin_updated",
    plugin_runtime_correlations.c.plugin_id,
    plugin_runtime_correlations.c.updated_at,
)
Index(
    "ix_plugin_delivery_attempts_due",
    plugin_delivery_attempts.c.status,
    plugin_delivery_attempts.c.next_retry_at,
)
Index(
    "ix_plugin_delivery_attempts_plugin_updated",
    plugin_delivery_attempts.c.plugin_id,
    plugin_delivery_attempts.c.updated_at,
)
Index(
    "ix_plugin_delivery_queue_due",
    plugin_delivery_queue.c.plugin_id,
    plugin_delivery_queue.c.status,
    plugin_delivery_queue.c.available_at,
)

plugin_package_activations = Table(
    "plugin_package_activations",
    metadata,
    Column("plugin_id", Text, primary_key=True),
    Column("digest", Text, nullable=False),
    Column("previous_digest", Text, nullable=True),
    Column("updated_at", Text, nullable=False),
    schema="management",
)

PLUGIN_TABLES = (
    plugin_package_activations,
    plugin_api_tokens,
    plugin_callback_registrations,
    plugin_capability_grant_sets,
    plugin_capability_grants,
    plugin_configuration,
    plugin_delivery_attempts,
    plugin_delivery_queue,
    plugin_event_cursors,
    plugin_installations,
    plugin_packages,
    plugin_quotas,
    plugin_repository_meta,
    plugin_runtime_correlations,
    plugin_runtime_leases,
    plugin_runtime_owner,
    plugin_scope_grants,
    plugin_secrets,
    plugin_state,
    plugin_state_audit,
    plugin_websocket_sessions,
)


def upgrade():
    bind = op.get_bind()
    for table in PLUGIN_TABLES:
        table.create(bind)
    op.execute(
        "INSERT INTO management.plugin_repository_meta(key,value) VALUES ('schema_version','4')"
    )


def downgrade():
    bind = op.get_bind()
    for table in reversed(PLUGIN_TABLES):
        table.drop(bind)
