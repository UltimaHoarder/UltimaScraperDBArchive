"""add_websites_table_to_site_schemas

Revision ID: f2c4e8a1b9d7
Revises: a2ce87f67ef9
Create Date: 2026-02-24 06:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f2c4e8a1b9d7"
down_revision: Union[str, Sequence[str], None] = "a2ce87f67ef9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Upgrade schema."""
    for schema in SITE_SCHEMAS:
        op.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.websites (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES {schema}.users(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_websites_user_url UNIQUE (user_id, url)
                )
                """
            )
        )
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS idx_websites_user_id ON {schema}.websites (user_id)"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    for schema in SITE_SCHEMAS:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {schema}.idx_websites_user_id"))
        op.execute(sa.text(f"DROP TABLE IF EXISTS {schema}.websites"))
