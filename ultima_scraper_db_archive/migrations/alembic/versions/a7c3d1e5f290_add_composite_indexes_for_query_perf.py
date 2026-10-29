"""add_composite_indexes_for_query_performance

Revision ID: a7c3d1e5f290
Revises: 1b9e08940bc5
Create Date: 2026-03-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3d1e5f290"
down_revision: Union[str, Sequence[str], None] = "1b9e08940bc5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Add composite indexes to speed up filtered user listing queries."""
    for schema in SCHEMAS:
        op.create_index(
            "idx_users_active_performer",
            "users",
            ["active", "performer"],
            unique=False,
            schema=schema,
        )
        op.create_index(
            "idx_subscriptions_user_id_active",
            "subscriptions",
            ["user_id", "active"],
            unique=False,
            schema=schema,
        )
        op.create_index(
            "idx_user_infos_price",
            "user_infos",
            ["price"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    """Remove composite indexes."""
    for schema in SCHEMAS:
        op.drop_index(
            "idx_user_infos_price",
            table_name="user_infos",
            schema=schema,
        )
        op.drop_index(
            "idx_subscriptions_user_id_active",
            table_name="subscriptions",
            schema=schema,
        )
        op.drop_index(
            "idx_users_active_performer",
            table_name="users",
            schema=schema,
        )
