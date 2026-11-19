"""Store job and task account ids as bigint.

A job's task names the account it runs as (``job_tasks.auth_id``, and the
job's ``jobs.user_auth_id``). Both were 32-bit, which holds OnlyFans ids but
not Fansly's 18-digit ones: archiving a finished Fansly task failed with
"integer out of range" and the job never completed. Every other account id in
the archive is already bigint. Both tables are small history tables; the
change rewrites them under a short lock.

Revision ID: c7d2e4f6a8b1
Revises: b5e1c9d3a7f2
Create Date: 2026-11-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2e4f6a8b1"
down_revision: Union[str, Sequence[str], None] = "b5e1c9d3a7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) in the management schema.
COLUMNS = (("job_tasks", "auth_id"), ("jobs", "user_auth_id"))
INT4_MAX = 2**31 - 1


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    for table, column in COLUMNS:
        # On a partitioned table this also changes every partition.
        op.alter_column(
            table,
            column,
            schema="management",
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Back to integer; refused while any stored id needs bigint."""
    op.execute("SET LOCAL lock_timeout='5s'")
    conn = op.get_bind()
    for table, column in COLUMNS:
        too_big = conn.execute(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM management.{table}"
                f" WHERE abs({column}) > {INT4_MAX})"
            )
        ).scalar()
        if too_big:
            raise RuntimeError(
                f"management.{table}.{column} holds ids beyond integer range"
            )
    for table, column in COLUMNS:
        op.alter_column(
            table,
            column,
            schema="management",
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=True,
        )
