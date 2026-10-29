"""add_ai_assisted_and_verified_to_user_infos

Revision ID: 0614b9710fa1
Revises: e4d7a8b9c0f1
Create Date: 2026-10-05 23:39:55.852467

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0614b9710fa1'
down_revision: Union[str, Sequence[str], None] = 'e4d7a8b9c0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")
COLUMNS: tuple[str, ...] = (
    "ai_assisted",
    "verified",
)


def upgrade() -> None:
    """Upgrade schema."""
    for schema in SITE_SCHEMAS:
        for column_name in COLUMNS:
            op.execute(
                sa.text(
                    f"ALTER TABLE {schema}.user_infos "
                    f"ADD COLUMN IF NOT EXISTS {column_name} BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            op.create_index(
                op.f(f"ix_{schema}_user_infos_{column_name}"),
                "user_infos",
                [column_name],
                unique=False,
                schema=schema,
                if_not_exists=True,
            )


def downgrade() -> None:
    """Downgrade schema."""
    for schema in SITE_SCHEMAS:
        for column_name in reversed(COLUMNS):
            op.drop_index(
                op.f(f"ix_{schema}_user_infos_{column_name}"),
                table_name="user_infos",
                schema=schema,
                if_exists=True,
            )
            op.drop_column("user_infos", column_name, schema=schema)
