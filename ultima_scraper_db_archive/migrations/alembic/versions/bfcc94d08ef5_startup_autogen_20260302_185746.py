"""startup_autogen_20260302_185746

Revision ID: bfcc94d08ef5
Revises: 52ae3b2424d1
Create Date: 2026-03-02 18:57:47.207782

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from ultima_scraper_db_archive.crypto import (
    encrypt_secret_value,
    is_encrypted_secret,
    validate_secret_crypto_configuration,
)


# revision identifiers, used by Alembic.
revision: str = "bfcc94d08ef5"
down_revision: Union[str, Sequence[str], None] = "52ae3b2424d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUTH_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")
_AUTH_COLUMNS: tuple[str, ...] = (
    "cookie",
    "x_bc",
    "authorization",
    "user_agent",
    "email",
    "password",
)


def _table_exists(bind: sa.engine.Connection, schema: str, table: str) -> bool:
    row = bind.execute(
        text("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            LIMIT 1
            """),
        {"schema": schema, "table": table},
    ).first()
    return row is not None


def _encrypt_schema_auths(bind: sa.engine.Connection, schema: str) -> int:
    if not _table_exists(bind, schema, "user_auths"):
        return 0

    select_sql = text(f"""
        SELECT id, "cookie", "x_bc", "authorization", "user_agent", "email", "password"
        FROM "{schema}"."user_auths"
        """)
    rows = bind.execute(select_sql).mappings().all()
    updated_rows = 0

    for values in rows:
        changes: dict[str, str] = {}
        for column in _AUTH_COLUMNS:
            raw_value = values.get(column)
            if not isinstance(raw_value, str) or not raw_value:
                continue
            if is_encrypted_secret(raw_value):
                continue
            encrypted = encrypt_secret_value(raw_value)
            if encrypted and encrypted != raw_value:
                changes[column] = encrypted

        if not changes:
            continue

        set_clause = ", ".join(f'"{column}" = :{column}' for column in changes)
        params = {"id": values["id"], **changes}
        bind.execute(
            text(f'UPDATE "{schema}"."user_auths" SET {set_clause} WHERE id = :id'),
            params,
        )
        updated_rows += 1

    return updated_rows


def upgrade() -> None:
    """Upgrade schema."""
    # No DDL is required (columns stay TEXT), but we do an idempotent
    # data backfill so existing plaintext auth values are encrypted at rest.
    validate_secret_crypto_configuration()
    bind = op.get_bind()
    total_updated = 0
    for schema in _AUTH_SCHEMAS:
        total_updated += _encrypt_schema_auths(bind, schema)
    # Transaction is handled by Alembic migration context.
    print(f"[bfcc94d08ef5] Encrypted user_auths rows updated: {total_updated}")


def downgrade() -> None:
    """Downgrade schema."""
    # Irreversible by design: decrypting secrets in-place is not safe to automate.
    pass
