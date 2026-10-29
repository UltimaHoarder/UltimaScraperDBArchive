"""Keep string site identifiers beside their BigInteger keys.

LoyalFans identifies users and content with opaque strings. Those rows use a
63-bit hash of the string as ``id`` and keep the string in ``external_id``.
OnlyFans and Fansly leave it null. The column is nullable with no default, so
adding it rewrites no table; lookups stay on ``id``, so it has no index.

Revision ID: c7b3857c294c
Revises: c8a3e5f71d26
Create Date: 2026-10-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7b3857c294c"
down_revision: Union[str, Sequence[str], None] = "c8a3e5f71d26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")
TABLES = (
    "users",
    "media",
    "x_stories",
    "x_posts",
    "x_messages",
    "mass_message_stats",
    "x_mass_messages",
    "comments",
)


def upgrade() -> None:
    """Add a nullable ``external_id`` to every table keyed by a site id."""
    # Each ADD COLUMN takes a brief ACCESS EXCLUSIVE lock; fail fast rather
    # than queue live scraper writes behind a long-running query.
    op.execute("SET LOCAL lock_timeout='5s'")
    for schema in SCHEMAS:
        for table in TABLES:
            op.add_column(
                table,
                sa.Column("external_id", sa.Text(), nullable=True),
                schema=schema,
            )


def downgrade() -> None:
    """Drop ``external_id`` from every site table."""
    op.execute("SET LOCAL lock_timeout='5s'")
    for schema in SCHEMAS:
        for table in TABLES:
            op.drop_column(table, "external_id", schema=schema)
