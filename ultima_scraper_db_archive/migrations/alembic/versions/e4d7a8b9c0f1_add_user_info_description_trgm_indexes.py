"""Add trigram indexes for user_infos and histo_user_infos description search.

Revision ID: e4d7a8b9c0f1
Revises: c7d2e84a19b6
Create Date: 2026-10-05 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e4d7a8b9c0f1"
down_revision: str | Sequence[str] | None = "c7d2e84a19b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Add non-blocking GIN trigram indexes to user_infos and histo_user_infos descriptions."""
    for schema in SCHEMAS:
        with op.get_context().autocommit_block():
            op.create_index(
                "idx_histo_user_infos_desc_trgm",
                "histo_user_infos",
                ["description"],
                unique=False,
                schema=schema,
                postgresql_using="gin",
                postgresql_ops={"description": "public.gin_trgm_ops"},
                postgresql_concurrently=True,
                if_not_exists=True,
            )
            op.create_index(
                "idx_user_infos_desc_trgm",
                "user_infos",
                ["description"],
                unique=False,
                schema=schema,
                postgresql_using="gin",
                postgresql_ops={"description": "public.gin_trgm_ops"},
                postgresql_where="description IS NOT NULL AND description != ''",
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    """Remove user_infos and histo_user_infos description trigram indexes."""
    for schema in reversed(SCHEMAS):
        with op.get_context().autocommit_block():
            op.drop_index(
                "idx_user_infos_desc_trgm",
                table_name="user_infos",
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
            op.drop_index(
                "idx_histo_user_infos_desc_trgm",
                table_name="histo_user_infos",
                schema=schema,
                postgresql_concurrently=True,
                if_exists=True,
            )
