"""Add post/message linkage columns to bought_content

Revision ID: e29a5f9a7c41
Revises: 870ab3e75443
Create Date: 2026-03-06 13:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e29a5f9a7c41"
down_revision: Union[str, Sequence[str], None] = "870ab3e75443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Upgrade schema."""
    for schema_name in SITE_SCHEMAS:
        op.add_column(
            "bought_content",
            sa.Column("post_id", sa.BigInteger(), nullable=True),
            schema=schema_name,
        )
        op.add_column(
            "bought_content",
            sa.Column("message_id", sa.BigInteger(), nullable=True),
            schema=schema_name,
        )
        op.create_foreign_key(
            f"fk_{schema_name}_bought_content_post_id",
            "bought_content",
            "x_posts",
            ["post_id"],
            ["id"],
            source_schema=schema_name,
            referent_schema=schema_name,
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            f"fk_{schema_name}_bought_content_message_id",
            "bought_content",
            "x_messages",
            ["message_id"],
            ["id"],
            source_schema=schema_name,
            referent_schema=schema_name,
            ondelete="CASCADE",
        )
        op.create_index(
            "idx_bought_content_post_id",
            "bought_content",
            ["post_id"],
            unique=False,
            schema=schema_name,
        )
        op.create_index(
            "idx_bought_content_message_id",
            "bought_content",
            ["message_id"],
            unique=False,
            schema=schema_name,
        )
        op.create_index(
            "idx_bought_content_buyer_post_id",
            "bought_content",
            ["buyer_id", "post_id"],
            unique=False,
            schema=schema_name,
        )
        op.create_index(
            "idx_bought_content_buyer_message_id",
            "bought_content",
            ["buyer_id", "message_id"],
            unique=False,
            schema=schema_name,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for schema_name in SITE_SCHEMAS:
        op.drop_index(
            "idx_bought_content_buyer_message_id",
            table_name="bought_content",
            schema=schema_name,
        )
        op.drop_index(
            "idx_bought_content_buyer_post_id",
            table_name="bought_content",
            schema=schema_name,
        )
        op.drop_index(
            "idx_bought_content_message_id",
            table_name="bought_content",
            schema=schema_name,
        )
        op.drop_index(
            "idx_bought_content_post_id",
            table_name="bought_content",
            schema=schema_name,
        )
        op.drop_constraint(
            f"fk_{schema_name}_bought_content_message_id",
            "bought_content",
            schema=schema_name,
            type_="foreignkey",
        )
        op.drop_constraint(
            f"fk_{schema_name}_bought_content_post_id",
            "bought_content",
            schema=schema_name,
            type_="foreignkey",
        )
        op.drop_column("bought_content", "message_id", schema=schema_name)
        op.drop_column("bought_content", "post_id", schema=schema_name)
