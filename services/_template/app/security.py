"""Service-to-service auth + event signing for the ``__BLOCK_ID__`` service.

Reuses the host's verified patterns verbatim in shape, but as a standalone
implementation (a Level-3 service does not import the host):

- **Service tokens** mirror ``backend/app/core/security.py`` — HS256 JWTs with an
  ``exp`` and a ``type`` discriminator (``"service"``), scoped to this block via
  ``aud``. See SERVICE_BLOCK_PATTERN.md §3.2.
- **Event signatures** mirror ``backend/app/core/webhook_security.py`` —
  HMAC-SHA256 over ``timestamp|body`` with a replay window. See §3.7.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings


# --------------------------------------------------------------------------- #
# Host -> service: signed service tokens (JWT, HS256)
# --------------------------------------------------------------------------- #
def create_service_token(
    *,
    workspace_id: int | str,
    block_id: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    """Mint a short-lived service token.

    **Host-side.** The host CRM calls this (or an equivalent on its side) and
    sends the result as ``Authorization: Bearer <token>`` to the service. Mirrors
    ``security.create_access_token``.
    """
    block_id = block_id or settings.block_id
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "type": "service",
        "aud": block_id,
        "workspace_id": str(workspace_id),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds or settings.service_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.service_token_secret, algorithm=settings.algorithm)


def decode_service_token(token: str) -> dict[str, Any]:
    """Verify a service token; raise ``jwt.InvalidTokenError`` on any failure.

    **Service-side.** Requires a valid signature, ``type == "service"``, the
    correct ``aud`` (this block), and an unexpired ``exp``.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.service_token_secret,
        algorithms=[settings.algorithm],
        audience=settings.block_id,
        options={"require": ["exp", "type"]},
    )
    if payload.get("type") != "service":
        raise jwt.InvalidTokenError("not a service token")
    return payload


# --------------------------------------------------------------------------- #
# Service -> host: signed event callbacks (HMAC-SHA256 over timestamp|body)
# --------------------------------------------------------------------------- #
def sign_event(body: bytes) -> tuple[str, str]:
    """Return ``(timestamp, signature)`` for an event body sent to the host."""
    timestamp = str(int(time.time()))
    signed = f"{timestamp}|".encode() + body
    signature = hmac.new(
        settings.service_token_secret.encode(), signed, hashlib.sha256
    ).hexdigest()
    return timestamp, signature


def verify_event(
    signature: str,
    timestamp: str,
    body: bytes,
    *,
    max_skew_seconds: int = 300,
) -> bool:
    """Verify an HMAC event signature + replay window (Cal.com-style)."""
    if not signature or not timestamp:
        return False
    try:
        if abs(int(time.time()) - int(timestamp)) > max_skew_seconds:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}|".encode() + body
    expected = hmac.new(
        settings.service_token_secret.encode(), signed, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def event_headers(body: bytes) -> dict[str, str]:
    """Convenience: headers to attach when POSTing a signed event to the host."""
    timestamp, signature = sign_event(body)
    return {"X-Service-Timestamp": timestamp, "X-Service-Signature": signature}
