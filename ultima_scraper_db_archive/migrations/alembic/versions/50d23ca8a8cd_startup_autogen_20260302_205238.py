"""startup_autogen_20260302_205238

Revision ID: 50d23ca8a8cd
Revises: bfcc94d08ef5
Create Date: 2026-03-02 20:52:38.823009

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "50d23ca8a8cd"
down_revision: Union[str, Sequence[str], None] = "bfcc94d08ef5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Intentionally no-op.
    # Secret-at-rest uses application-layer encryption/decryption while DB
    # columns remain TEXT. No physical DDL is required for this revision.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Intentionally no-op (see upgrade()).
    pass
