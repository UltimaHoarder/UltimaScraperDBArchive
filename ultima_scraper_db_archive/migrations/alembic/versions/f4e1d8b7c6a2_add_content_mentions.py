"""Add general archived-content mentions.

Revision ID: f4e1d8b7c6a2
Revises: c9d4e8f2a6b1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4e1d8b7c6a2"
down_revision: Union[str, Sequence[str], None] = "c9d4e8f2a6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for schema in SCHEMAS:
        table_exists = inspector.has_table("content_mentions", schema=schema)
        if not table_exists:
            op.create_table(
                "content_mentions",
                sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
                sa.Column("post_id", sa.BigInteger(), nullable=True),
                sa.Column("message_id", sa.BigInteger(), nullable=True),
                sa.Column("mass_message_id", sa.BigInteger(), nullable=True),
                sa.Column("story_id", sa.BigInteger(), nullable=True),
                sa.Column("mentioned_user_id", sa.BigInteger(), nullable=True),
                sa.Column("raw_mention", sa.Text(), nullable=False),
                sa.Column("normalized_mention", sa.String(length=512), nullable=False),
                sa.Column("mention_kind", sa.String(length=32), server_default="platform_tag", nullable=False),
                sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
                sa.CheckConstraint("num_nonnulls(post_id, message_id, mass_message_id, story_id) = 1", name="ck_content_mentions_one_content"),
                sa.ForeignKeyConstraint(["post_id"], [f"{schema}.x_posts.id"], ondelete="CASCADE"),
                sa.ForeignKeyConstraint(["message_id"], [f"{schema}.x_messages.id"], ondelete="CASCADE"),
                sa.ForeignKeyConstraint(["mass_message_id"], [f"{schema}.x_mass_messages.id"], ondelete="CASCADE"),
                sa.ForeignKeyConstraint(["story_id"], [f"{schema}.x_stories.id"], ondelete="CASCADE"),
                sa.ForeignKeyConstraint(["mentioned_user_id"], [f"{schema}.users.id"], ondelete="SET NULL"),
                sa.PrimaryKeyConstraint("id"),
                schema=schema,
            )
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("content_mentions", schema=schema)
        } if table_exists else set()
        for column in ("post_id", "message_id", "mass_message_id", "story_id", "mentioned_user_id", "normalized"):
            name = f"idx_content_mentions_{column}"
            if name not in existing_indexes:
                op.create_index(name, "content_mentions", [f"{column}_mention" if column == "normalized" else column], schema=schema)
        # Keep the old rows as content-level evidence before the legacy table
        # is retired.  User IDs resolve to their current username here while
        # preserving a useful fallback if historical user data is incomplete.
        op.execute(
            sa.text(
                f"""
                INSERT INTO {schema}.content_mentions
                    (post_id, mentioned_user_id, raw_mention, normalized_mention, mention_kind)
                SELECT linked.post_id,
                       linked.linked_user_id,
                       COALESCE(users.username, linked.linked_user_id::text),
                       lower(COALESCE(users.username, linked.linked_user_id::text)),
                       'platform_tag'
                FROM {schema}.linked_users AS linked
                LEFT JOIN {schema}.users AS users ON users.id = linked.linked_user_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM {schema}.content_mentions AS mention
                    WHERE mention.post_id = linked.post_id
                      AND mention.mentioned_user_id = linked.linked_user_id
                      AND mention.mention_kind = 'platform_tag'
                )
                """
            )
        )


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.drop_table("content_mentions", schema=schema)
