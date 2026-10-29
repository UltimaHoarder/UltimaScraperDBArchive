from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator
from ultima_scraper_core import runtime_env_value

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:v1:"
_secret_decrypt_failure_observer: Callable[[], None] | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = runtime_env_value(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _security_mode() -> str:
    return (runtime_env_value("SECURITY_ENFORCEMENT") or "strict").strip().lower()


def set_secret_decrypt_failure_observer(
    observer: Callable[[], None] | None,
) -> None:
    """Register an application-owned observer without importing the application."""

    global _secret_decrypt_failure_observer
    _secret_decrypt_failure_observer = observer


def _increment_secret_decrypt_failure_metric() -> None:
    observer = _secret_decrypt_failure_observer
    if observer is None:
        return
    try:
        observer()
    except Exception:
        pass


def is_secret_encryption_enabled() -> bool:
    return _env_bool("USR_ENCRYPT_SECRETS", True)


def _derive_fernet_key(raw: str) -> bytes:
    candidate = raw.strip().encode()
    try:
        decoded = base64.urlsafe_b64decode(candidate)
        if len(decoded) == 32:
            return candidate
    except Exception:
        pass
    digest = hashlib.sha256(candidate).digest()
    return base64.urlsafe_b64encode(digest)


class SecretCrypto:
    def __init__(self, current_key: str, previous_key: str | None = None) -> None:
        from cryptography.fernet import Fernet

        self._current = Fernet(_derive_fernet_key(current_key))
        self._previous = (
            Fernet(_derive_fernet_key(previous_key))
            if previous_key and previous_key.strip()
            else None
        )

    def encrypt(self, plaintext: str) -> str:
        token = self._current.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt(self, ciphertext: str) -> str:
        token = (
            ciphertext[len(ENC_PREFIX) :]
            if ciphertext.startswith(ENC_PREFIX)
            else ciphertext
        )
        encoded = token.encode("utf-8")

        try:
            return self._current.decrypt(encoded).decode("utf-8")
        except Exception:
            if self._previous is None:
                raise
            return self._previous.decrypt(encoded).decode("utf-8")


def is_encrypted_secret(value: str | None) -> bool:
    return bool(value and value.startswith(ENC_PREFIX))


@lru_cache(maxsize=1)
def get_secret_crypto() -> SecretCrypto | None:
    if not is_secret_encryption_enabled():
        return None
    key = (runtime_env_value("USR_SECRET_KEY") or "").strip()
    if not key:
        return None
    prev = runtime_env_value("USR_SECRET_KEY_PREVIOUS")
    return SecretCrypto(key, prev)


def validate_secret_crypto_configuration() -> None:
    if not is_secret_encryption_enabled():
        return
    key = (runtime_env_value("USR_SECRET_KEY") or "").strip()
    if not key:
        if _security_mode() == "report_only":
            logger.warning(
                "USR_SECRET_KEY missing while USR_ENCRYPT_SECRETS is enabled (report-only)"
            )
            return
        raise RuntimeError(
            "USR_SECRET_KEY is required when USR_ENCRYPT_SECRETS is enabled"
        )


def encrypt_secret_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not value:
        return value
    if is_encrypted_secret(value):
        return value
    crypto = get_secret_crypto()
    if crypto is None:
        return value
    return crypto.encrypt(value)


def decrypt_secret_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not is_encrypted_secret(value):
        return value
    crypto = get_secret_crypto()
    if crypto is None:
        _increment_secret_decrypt_failure_metric()
        raise RuntimeError(
            "Encountered encrypted secret value but USR_SECRET_KEY is not configured"
        )
    try:
        return crypto.decrypt(value)
    except Exception:
        _increment_secret_decrypt_failure_metric()
        raise


class EncryptedText(TypeDecorator[str]):
    """Transparent encryption at rest for SQLAlchemy text columns."""

    from sqlalchemy import Text

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        from sqlalchemy import Text

        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return encrypt_secret_value(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        try:
            return decrypt_secret_value(value)
        except Exception:
            logger.exception("Failed to decrypt secret value from database")
            raise
