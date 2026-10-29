"""add filepath lookup index

Revision ID: c9d4e8f2a6b1
Revises: b4f2a1c9e8d3
Create Date: 2026-08-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c9d4e8f2a6b1"
down_revision: Union[str, Sequence[str], None] = "b4f2a1c9e8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.create_index(
            "idx_filepaths_filepath",
            "filepaths",
            ["filepath"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    for schema in SCHEMAS:
        op.drop_index(
            "idx_filepaths_filepath",
            table_name="filepaths",
            schema=schema,
        )
