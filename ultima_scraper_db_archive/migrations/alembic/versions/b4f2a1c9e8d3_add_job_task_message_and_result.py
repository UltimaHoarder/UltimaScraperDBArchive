"""add job_tasks.message and result_json for archived task output

Revision ID: b4f2a1c9e8d3
Revises: e8c608daf25e
Create Date: 2026-04-22 00:00:00.000000

Rationale: task-level download errors (download_results[]) and the
human-readable success message were only kept in Redis and lost on
retention cleanup. Persist them alongside the archived task row so the
Pipeline / Errors tabs survive Redis purge.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4f2a1c9e8d3"
down_revision: Union[str, Sequence[str], None] = "e8c608daf25e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_tasks",
        sa.Column("message", sa.Text(), nullable=True),
        schema="management",
    )
    op.add_column(
        "job_tasks",
        sa.Column("result_json", sa.Text(), nullable=True),
        schema="management",
    )


def downgrade() -> None:
    op.drop_column("job_tasks", "result_json", schema="management")
    op.drop_column("job_tasks", "message", schema="management")
