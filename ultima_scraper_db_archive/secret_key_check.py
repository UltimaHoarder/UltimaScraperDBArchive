"""Make every backend and worker on one database use the same USR_SECRET_KEY.

They all read the secrets each other encrypted, such as auth cookies. One with
a different key can't read them, and what it writes can't be read by the rest.
So ``management.cluster.secret_key_check`` holds a fixed value encrypted with
the cluster's key, and a process whose key can't decrypt it refuses to start.

The first process to check fills it in. On a database that already holds
encrypted secrets, its key must open one of them first, so a new backend with
the wrong key can't claim the cluster. During a key rotation
(``USR_SECRET_KEY_PREVIOUS`` set to the old key) the check is re-encrypted with
the new key, after which a process with only the old key is refused.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from .crypto import SecretCrypto, get_secret_crypto

logger = logging.getLogger(__name__)

CHECK_VALUE = "ultimascraper:secret-key-check:v1"

_SELECT_CHECK = text("SELECT secret_key_check FROM management.cluster WHERE id = 1")
_ENSURE_ROW = text(
    "INSERT INTO management.cluster (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
)
_CLAIM_CHECK = text(
    "UPDATE management.cluster SET secret_key_check = :check "
    "WHERE id = 1 AND secret_key_check IS NULL"
)
_ROTATE_CHECK = text(
    "UPDATE management.cluster SET secret_key_check = :check "
    "WHERE id = 1 AND secret_key_check = :old"
)
# Every site schema keeps its encrypted auth cookies in user_auths.
_COOKIE_TABLES = text(
    "SELECT table_schema FROM information_schema.columns "
    "WHERE table_name = 'user_auths' AND column_name = 'cookie' "
    "ORDER BY table_schema"
)


class SecretKeyMismatch(RuntimeError):
    """This process's USR_SECRET_KEY differs from the rest of the cluster's."""


def _mismatch(reason: str) -> SecretKeyMismatch:
    return SecretKeyMismatch(
        f"USR_SECRET_KEY {reason}. Every backend and worker that shares this "
        "PostgreSQL database must use the same USR_SECRET_KEY. Copy it from a "
        "running backend (Docker: docker compose exec backend cat "
        "/home/ultimascraper/.config/ultima_scraper_verse/secrets/USR_SECRET_KEY) "
        "and set it in this host's .env. To change the key on purpose, set the "
        "old one as USR_SECRET_KEY_PREVIOUS."
    )


def _opens_existing_secrets(connection: Any, crypto: SecretCrypto) -> bool:
    """Whether this key opens the secrets already stored; True when there are none."""
    sampled = False
    for (schema,) in connection.execute(_COOKIE_TABLES).all():
        quoted = '"' + str(schema).replace('"', '""') + '"'
        rows = connection.execute(
            text(
                f"SELECT cookie FROM {quoted}.user_auths "
                "WHERE cookie LIKE 'enc:v1:%' LIMIT 3"
            )
        ).scalars()
        for value in rows:
            sampled = True
            try:
                crypto.decrypt(value)
            except Exception:
                continue
            return True
    return not sampled


def verify_secret_key(connection: Any) -> None:
    """Check this process's key against the cluster's; record it if none is.

    Takes a synchronous SQLAlchemy connection and commits on it. Does nothing
    when secret encryption is off or the schema predates the check. Raises
    :class:`SecretKeyMismatch` when the key differs from the cluster's.
    """
    crypto = get_secret_crypto()
    if crypto is None:
        # Encryption is off, or the missing key is reported by
        # validate_secret_crypto_configuration.
        return
    try:
        connection.execute(_ENSURE_ROW)
        stored = connection.execute(_SELECT_CHECK).scalar()
    except ProgrammingError:
        # No management.cluster or no column yet: setup migrates the schema
        # and the check runs again then.
        connection.rollback()
        logger.debug("This database has no secret key check yet", exc_info=True)
        return

    if stored is None:
        if not _opens_existing_secrets(connection, crypto):
            connection.rollback()
            raise _mismatch("can't decrypt the secrets already stored in this database")
        connection.execute(_CLAIM_CHECK, {"check": crypto.encrypt(CHECK_VALUE)})
        connection.commit()
        # Another process may have claimed it first; check against the winner.
        stored = connection.execute(_SELECT_CHECK).scalar()

    try:
        opened = crypto.decrypt(stored)
    except Exception:
        connection.rollback()
        raise _mismatch("is not the key the other backends on this database use") from None
    if opened != CHECK_VALUE:
        connection.rollback()
        raise _mismatch("is not the key the other backends on this database use")

    if not crypto.decrypts_with_current(stored):
        # Opened only with USR_SECRET_KEY_PREVIOUS: the cluster is rotating.
        connection.execute(
            _ROTATE_CHECK, {"check": crypto.encrypt(CHECK_VALUE), "old": stored}
        )
        logger.info("Moved the cluster's secret key check to the new USR_SECRET_KEY")
    connection.commit()


def verify_secret_key_for_engine(engine: Any) -> None:
    """:func:`verify_secret_key` on a fresh connection from ``engine``."""
    with engine.connect() as connection:
        verify_secret_key(connection)
