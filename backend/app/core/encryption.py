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
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a valid 32-byte Fernet key from an arbitrary secret string.

    Uses PBKDF2-HMAC-SHA256 with 310,000 iterations (OWASP 2024 minimum)
    and a deterministic salt derived from the secret itself, ensuring
    backwards compatibility without needing to store a separate salt.
    """
    salt = hashlib.sha256(secret.encode()).digest()[:16]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=310_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


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
