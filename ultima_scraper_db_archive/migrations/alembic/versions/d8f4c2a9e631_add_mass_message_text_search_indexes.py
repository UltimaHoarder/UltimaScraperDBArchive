"""Add trigram indexes for mass-message text search.

Revision ID: d8f4c2a9e631
Revises: 52aabfd5b7a9
Create Date: 2026-08-16 04:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8f4c2a9e631"
down_revision: str | Sequence[str] | None = "52aabfd5b7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")
INDEX_NAME = "idx_x_mass_messages_text_trgm"


def upgrade() -> None:
    """Add non-blocking GIN trigram indexes to searchable mass messages."""
    for schema in SCHEMAS:
        with op.get_context().autocommit_block():
            op.create_index(
                INDEX_NAME,
                "x_mass_messages",
                ["text"],
                unique=False,
                schema=schema,
                postgresql_using="gin",
                postgresql_ops={"text": "public.gin_trgm_ops"},
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    """Remove the mass-message text-search indexes without blocking writes."""
    for schema in reversed(SCHEMAS):
        with op.get_context().autocommit_block():
            op.drop_index(
                INDEX_NAME,
                table_name="x_mass_messages",
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
