"""Brand-local outbound credentials; an existing connection is authoritative.

Legacy platform-managed transport is allowed only when no brand row exists.
Never infer a brand from membership, organization, or another connection.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

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
            sender = values.get("from_email")
            if (
                not isinstance(sender, str)
                or "@" not in sender
                or any(c in sender for c in "\r\n<>")
            ):
                raise IntegrationCredentialError("Configure this brand's Resend sender email.")
            name = values.get("from_name", "")
            if not isinstance(name, str) or any(c in name for c in "\r\n"):
                raise IntegrationCredentialError("Configure a valid brand sender name.")
        return OutboundCredentials(key.strip(), "workspace", values)

    key = settings.telnyx_api_key if provider == "telnyx" else settings.resend_api_key
    if not allow_platform_fallback or not key:
        raise IntegrationCredentialError(
            f"Connect {provider} for this brand in Settings → Integrations."
        )
    return OutboundCredentials(key, "platform", {})


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
