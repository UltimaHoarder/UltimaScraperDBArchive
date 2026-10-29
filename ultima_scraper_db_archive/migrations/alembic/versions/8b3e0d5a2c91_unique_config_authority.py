"""One canonical config and scope mapping per backend.

Existing duplicates deliberately fail the index build and require review.
"""

import sqlalchemy as sa
from alembic import op

revision = "8b3e0d5a2c91"
down_revision = "7a2d9c4e1f80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_settings_config_authority",
        "settings",
        ["backend", "key"],
        unique=True,
        schema="management",
        postgresql_where=sa.text("key IN ('config', 'config_scope')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_settings_config_authority", table_name="settings", schema="management"
    )
