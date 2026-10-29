"""startup_autogen_20260302_210630

Revision ID: 7f3bb03678e1
Revises: 50d23ca8a8cd
Create Date: 2026-03-02 21:06:31.258297

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "7f3bb03678e1"
down_revision: Union[str, Sequence[str], None] = "50d23ca8a8cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Intentionally no-op.
    # EncryptedText uses TEXT storage; no DDL is needed for this revision.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Intentionally no-op (see upgrade()).
    pass
