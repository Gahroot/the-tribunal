"""Application-layer encryption for sensitive data (integration credentials, API keys).

Uses Fernet symmetric encryption derived from the ENCRYPTION_KEY setting.
Fernet guarantees that data encrypted with it cannot be read or tampered with
without the key, and provides built-in timestamp-based token expiration support.
"""

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a valid 32-byte Fernet key from an arbitrary secret string.

    Uses SHA-256 to produce a deterministic 32-byte key, then base64-encodes
    it as required by Fernet (url-safe base64 of 32 bytes = 44 chars).
    """
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the configured encryption key."""
    key = _derive_fernet_key(settings.encryption_key)
    return Fernet(key)


def encrypt_json(data: dict[str, Any]) -> str:
    """Encrypt a dict as a Fernet-encrypted string.

    Args:
        data: Dictionary to encrypt (must be JSON-serializable).

    Returns:
        Base64-encoded encrypted token string (safe for TEXT column storage).
    """
    plaintext = json.dumps(data, separators=(",", ":")).encode()
    return _get_fernet().encrypt(plaintext).decode()


def decrypt_json(encrypted: str) -> dict[str, Any]:
    """Decrypt a Fernet-encrypted string back to a dict.

    Args:
        encrypted: Fernet token string produced by encrypt_json.

    Returns:
        The original dictionary.

    Raises:
        InvalidToken: If the token is invalid or the key doesn't match.
    """
    plaintext = _get_fernet().decrypt(encrypted.encode())
    result: dict[str, Any] = json.loads(plaintext)
    return result


__all__ = ["InvalidToken", "decrypt_json", "encrypt_json"]
