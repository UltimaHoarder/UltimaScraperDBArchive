"""Keep the tax a site adds to a spender's wallet payments.

OnlyFans charges sales tax on top of a price and takes it from the same wallet,
so the balance overstates what an account can buy. The column is nullable with
no default, so adding it rewrites no table; null means it hasn't been asked yet.

Revision ID: f3b7d2a84c16
Revises: e8a3f5c2b694
Create Date: 2026-11-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b7d2a84c16"
down_revision: Union[str, Sequence[str], None] = "e8a3f5c2b694"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Add a nullable ``wallet_tax_percent`` to every site's users."""
    op.execute("SET LOCAL lock_timeout='5s'")
    for schema in SCHEMAS:
        op.add_column(
            "users",
            sa.Column("wallet_tax_percent", sa.Float(), nullable=True),
            schema=schema,
        )


def downgrade() -> None:
    """Drop ``wallet_tax_percent`` from every site's users."""
    op.execute("SET LOCAL lock_timeout='5s'")
    for schema in SCHEMAS:
        op.drop_column("users", "wallet_tax_percent", schema=schema)
