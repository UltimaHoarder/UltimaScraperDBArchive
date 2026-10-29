"""Make bought_content buyer-content links unique

Revision ID: c4a5f16d7e2b
Revises: 1b9e08940bc5
Create Date: 2026-03-12 12:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a5f16d7e2b"
down_revision: Union[str, Sequence[str], None] = "1b9e08940bc5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")


def _delete_duplicate_links(schema_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY buyer_id, {column_name}
                        ORDER BY id
                    ) AS rn
                FROM {schema_name}.bought_content
                WHERE {column_name} IS NOT NULL
            )
            DELETE FROM {schema_name}.bought_content AS bought_content
            USING ranked
            WHERE bought_content.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )


def upgrade() -> None:
    """Upgrade schema."""
    for schema_name in SITE_SCHEMAS:
        _delete_duplicate_links(schema_name, "post_id")
        _delete_duplicate_links(schema_name, "message_id")

        op.drop_index(
            "idx_bought_content_buyer_post_id",
            table_name="bought_content",
            schema=schema_name,
        )
        op.drop_index(
            "idx_bought_content_buyer_message_id",
            table_name="bought_content",
            schema=schema_name,
        )

        op.create_index(
            "idx_bought_content_buyer_post_id",
            "bought_content",
            ["buyer_id", "post_id"],
            unique=True,
            schema=schema_name,
        )
        op.create_index(
            "idx_bought_content_buyer_message_id",
            "bought_content",
            ["buyer_id", "message_id"],
            unique=True,
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
