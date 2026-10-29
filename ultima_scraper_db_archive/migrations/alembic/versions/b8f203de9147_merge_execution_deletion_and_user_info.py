"""Merge execution deletion indexes and user-info migrations.

Revision ID: b8f203de9147
Revises: a6d901fe7823, 0614b9710fa1
"""

revision = "b8f203de9147"
down_revision = ("a6d901fe7823", "0614b9710fa1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join both migration branches without additional schema changes."""


def downgrade() -> None:
    """Restore the two branch heads without additional schema changes."""
