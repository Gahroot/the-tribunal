"""Brand-local outbound credentials; an existing connection is authoritative.

Legacy platform-managed transport is allowed only when no brand row exists.
Never infer a brand from membership, organization, or another connection.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import WorkspaceIntegration


class IntegrationCredentialError(ValueError):
    """An actionable failure, containing no secret values."""


@dataclass(frozen=True, slots=True)
class OutboundCredentials:
    api_key: str = field(repr=False)
    source: Literal["workspace", "platform"]
    values: dict[str, Any] = field(repr=False)


def validate_email_sender(values: dict[str, Any]) -> None:
    """Validate header syntax, not domain ownership (Resend enforces verification)."""
    sender = values.get("from_email")
    name = values.get("from_name", "")
    if (
        not isinstance(sender, str)
        or any(c in sender for c in "\r\n<>")
        or not isinstance(name, str)
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        raise IntegrationCredentialError("Configure a valid Resend sender email and name.")
    try:
        TypeAdapter(EmailStr).validate_python(sender)
    except ValidationError as exc:
        raise IntegrationCredentialError("Configure a valid Resend sender email.") from exc


def outbound_credentials_from_record(
    integration: WorkspaceIntegration | None,
    provider: Literal["telnyx", "resend"],
    *,
    allow_platform_fallback: bool = True,
) -> OutboundCredentials:
    """Use the same account selection for settings readiness and execution."""
    if integration is not None:
        if not integration.is_active:
            raise IntegrationCredentialError(f"The brand's {provider} connection is disabled.")
        values = integration.safe_credentials()
        if not isinstance(values, dict):
            raise IntegrationCredentialError(
                f"Re-enter the brand's unreadable {provider} credentials."
            )
        key = values.get("api_key")
        if not isinstance(key, str) or not key.strip():
            raise IntegrationCredentialError(f"The brand's {provider} connection needs an API key.")
        if provider == "resend":
            validate_email_sender(values)
        return OutboundCredentials(key.strip(), "workspace", values)

    key = settings.telnyx_api_key if provider == "telnyx" else settings.resend_api_key
    if not allow_platform_fallback or not key:
        raise IntegrationCredentialError(
            f"Connect {provider} for this brand in Settings → Integrations."
        )
    platform_values: dict[str, Any] = {}
    if provider == "resend":
        platform_values = {
            "from_email": settings.resend_from_email,
            "from_name": settings.resend_from_name or "The Tribunal",
        }
        validate_email_sender(platform_values)
        if platform_values["from_email"] == "noreply@example.com":
            raise IntegrationCredentialError("Configure the platform's verified Resend sender.")
    return OutboundCredentials(key, "platform", platform_values)


async def resolve_outbound_credentials(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    provider: Literal["telnyx", "resend"],
    *,
    allow_platform_fallback: bool = True,
) -> OutboundCredentials:
    """Resolve only the explicitly supplied brand; never cache secret-bearing clients."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.integration_type == provider,
        )
    )
    return outbound_credentials_from_record(
        result.scalar_one_or_none(), provider, allow_platform_fallback=allow_platform_fallback
    )
