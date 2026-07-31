"""Envelope encryption for user-supplied provider API keys.

Bring-your-own-key is a core part of the product, which means the platform holds
other people's paid credentials. They are encrypted at rest with a key that lives
only in the environment, never in the database.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class SecretBoxError(RuntimeError):
    pass


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        # Derive a stable development key from the app secret so `mock` mode runs
        # out of the box. Production must set FORGECAST_ENCRYPTION_KEY explicitly.
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:  # malformed key
        raise SecretBoxError(f"invalid FORGECAST_ENCRYPTION_KEY: {exc}") from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise SecretBoxError(
            "could not decrypt stored secret — the encryption key changed"
        ) from exc


def fingerprint(plaintext: str) -> str:
    """Short non-reversible tag so the UI can show *which* key is stored."""
    return hashlib.sha256(plaintext.encode()).hexdigest()[:8]


def mask(plaintext: str) -> str:
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}…{plaintext[-4:]}"
