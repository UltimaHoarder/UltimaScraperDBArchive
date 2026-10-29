"""Preserve ordinary job configuration and task inputs for archived retry.

Revision ID: f17b9e204ca6
Revises: e25ac8106df4
"""

from alembic import op
import sqlalchemy as sa

revision = "f17b9e204ca6"
down_revision = "e25ac8106df4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("job_config_json", sa.Text(), nullable=True), schema="management")
    op.add_column("job_tasks", sa.Column("definition_json", sa.Text(), nullable=True), schema="management")


def downgrade():
    op.drop_column("job_tasks", "definition_json", schema="management")
    op.drop_column("jobs", "job_config_json", schema="management")
