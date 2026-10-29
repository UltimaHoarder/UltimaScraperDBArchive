"""add_profile_type_sexual_content_partner_identity

Revision ID: e3f1a2b4c5d6
Revises: d2c4f71a6b90
Create Date: 2026-09-30 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3f1a2b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d2c4f71a6b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")
COLUMNS: tuple[str, ...] = (
    "profile_type",
    "sexual_content",
    "partner_sex",
    "partner_gender",
)


def upgrade() -> None:
    for schema in SITE_SCHEMAS:
        for column_name in COLUMNS:
            op.execute(
                sa.text(
                    f"ALTER TABLE {schema}.user_infos "
                    f"ADD COLUMN IF NOT EXISTS {column_name} SMALLINT"
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
    for schema in SITE_SCHEMAS:
        for column_name in reversed(COLUMNS):
            op.drop_index(
                op.f(f"ix_{schema}_user_infos_{column_name}"),
                table_name="user_infos",
                schema=schema,
                if_exists=True,
            )
            op.drop_column("user_infos", column_name, schema=schema)
