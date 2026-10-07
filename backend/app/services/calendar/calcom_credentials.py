"""Workspace-scoped Cal.com credential resolution.

Single source of truth for "which Cal.com API key does this workspace book
with?". Every booking-readiness gate and booking execution path (text tools,
voice tools, approved pending actions) resolves through here so an operator who
saves a Cal.com key in Settings → Integrations gets working AI booking without
any extra environment setup.

Resolution order for a workspace:

1. The workspace's own ``calcom`` :class:`WorkspaceIntegration` row (Fernet
   encrypted with ``ENCRYPTION_KEY``). When a row exists it is authoritative:
   an inactive, unreadable, or key-less row fails closed with an actionable
   error rather than silently booking on a different Cal.com account.
2. Documented global fallback: ``settings.calcom_api_key`` (``CALCOM_API_KEY``)
   is used **only** when the workspace has never saved a Cal.com connection.
   This keeps legacy single-tenant deployments working; it never overrides or
   backs up a workspace-specific connection.

The API key is never logged. Only ``workspace_id``, ``source`` and error codes
are emitted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_json
from app.db.scope import apply_workspace_scope
from app.models.workspace import WorkspaceIntegration

logger = structlog.get_logger()

CALCOM_INTEGRATION_TYPE = "calcom"

CalComCredentialSource = Literal["workspace", "global"]

# Machine-readable error codes surfaced to tool results / approval results.
CALCOM_NOT_CONNECTED = "calcom_not_connected"
CALCOM_INTEGRATION_INACTIVE = "calcom_integration_inactive"
CALCOM_CREDENTIALS_UNREADABLE = "calcom_credentials_unreadable"
CALCOM_API_KEY_MISSING = "calcom_api_key_missing"
CALCOM_AUTH_FAILED = "calcom_auth_failed"
CALCOM_EVENT_TYPE_MISSING = "calcom_event_type_missing"
CALCOM_EVENT_TYPE_NOT_FOUND = "calcom_event_type_not_found"
CALCOM_PROVIDER_ERROR = "calcom_provider_error"

_SETTINGS_HINT = "in Settings → Integrations → Cal.com"


@dataclass(frozen=True, slots=True)
class CalComCredentials:
    """Resolved Cal.com credentials. ``api_key`` is secret — never log this object."""

    api_key: str = field(repr=False)
    source: CalComCredentialSource


class CalComCredentialError(Exception):
    """Raised when a workspace has no usable Cal.com credentials."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_result(self) -> dict[str, object]:
        """Tool/approval-friendly failure payload."""
        return {"success": False, "error": self.message, "error_code": self.code}


def _global_credentials() -> CalComCredentials | None:
    key = settings.calcom_api_key
    return CalComCredentials(api_key=key, source="global") if key else None


async def resolve_calcom_credentials(
    db: AsyncSession | None,
    workspace_id: uuid.UUID | None,
    *,
    allow_global_fallback: bool = True,
) -> CalComCredentials:
    """Resolve the Cal.com credentials a workspace should book with.

    Raises:
        CalComCredentialError: with a distinct ``code`` for not connected,
            inactive, undecryptable, or key-less connections.
    """
    if workspace_id is None or db is None:
        fallback = _global_credentials() if allow_global_fallback else None
        if fallback is None:
            raise CalComCredentialError(
                CALCOM_NOT_CONNECTED,
                f"Cal.com is not connected. Add a Cal.com API key {_SETTINGS_HINT}.",
            )
        return fallback

    result = await db.execute(
        apply_workspace_scope(
            select(WorkspaceIntegration),
            WorkspaceIntegration,
            workspace_id,
        ).where(WorkspaceIntegration.integration_type == CALCOM_INTEGRATION_TYPE)
    )
    integration = result.scalar_one_or_none()
    log = logger.bind(workspace_id=str(workspace_id), integration_type=CALCOM_INTEGRATION_TYPE)

    if integration is None:
        fallback = _global_credentials() if allow_global_fallback else None
        if fallback is not None:
            log.info("calcom_credentials_resolved", source="global")
            return fallback
        raise CalComCredentialError(
            CALCOM_NOT_CONNECTED,
            f"Cal.com is not connected for this workspace. Add a Cal.com API key {_SETTINGS_HINT}.",
        )

    if not integration.is_active:
        raise CalComCredentialError(
            CALCOM_INTEGRATION_INACTIVE,
            "The Cal.com connection for this workspace is disabled. "
            f"Re-enable it {_SETTINGS_HINT}.",
        )

    try:
        credentials = decrypt_json(integration.encrypted_credentials)
    except (InvalidToken, ValueError, TypeError) as exc:
        log.warning("calcom_credentials_decrypt_failed", error_type=type(exc).__name__)
        raise CalComCredentialError(
            CALCOM_CREDENTIALS_UNREADABLE,
            "The saved Cal.com credentials could not be decrypted. "
            f"Re-enter the Cal.com API key {_SETTINGS_HINT}.",
        ) from exc

    api_key = credentials.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise CalComCredentialError(
            CALCOM_API_KEY_MISSING,
            f"The saved Cal.com connection has no API key. Add one {_SETTINGS_HINT}.",
        )

    log.debug("calcom_credentials_resolved", source="workspace")
    return CalComCredentials(api_key=api_key.strip(), source="workspace")


async def calcom_credentials_ready(db: AsyncSession, workspace_id: uuid.UUID | None) -> bool:
    """Readiness gate: True when the workspace can authenticate to Cal.com."""
    try:
        await resolve_calcom_credentials(db, workspace_id)
    except CalComCredentialError:
        return False
    return True
