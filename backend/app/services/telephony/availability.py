"""Workspace telephony availability helpers."""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workspace import WorkspaceIntegration

TELEPHONY_PROVIDER: Literal["telnyx"] = "telnyx"
TELEPHONY_UNAVAILABLE_CODE = "telephony_unavailable"
TELEPHONY_SETUP_ACTION_LABEL = "Open integrations settings"
TELEPHONY_SETUP_ACTION_HREF = "/settings?tab=integrations"
TELEPHONY_UNAVAILABLE_MESSAGE = (
    "Telephony is not enabled for this workspace. Ask an admin to connect Telnyx "
    "in Settings > Integrations before adding SMS or voice numbers."
)
TELEPHONY_ENABLED_MESSAGE = (
    "Telephony is enabled. You can search, purchase, and sync Telnyx phone numbers."
)


async def get_telnyx_api_key_for_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> str | None:
    """Return the server or workspace Telnyx API key available to a workspace."""
    server_key = settings.telnyx_api_key.strip()
    if server_key:
        return server_key

    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.integration_type == TELEPHONY_PROVIDER,
            WorkspaceIntegration.is_active.is_(True),
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        return None

    credentials = integration.safe_credentials()
    if credentials is None:
        return None

    api_key = credentials.get("api_key")
    if not isinstance(api_key, str):
        return None

    api_key = api_key.strip()
    return api_key or None


async def is_telephony_enabled_for_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> bool:
    """Return whether Telnyx-backed telephony actions are available."""
    return bool(await get_telnyx_api_key_for_workspace(db, workspace_id))


def telephony_unavailable_detail() -> dict[str, object]:
    """Structured error detail for clients to render actionable setup guidance."""
    return {
        "code": TELEPHONY_UNAVAILABLE_CODE,
        "message": TELEPHONY_UNAVAILABLE_MESSAGE,
        "details": {
            "action_label": TELEPHONY_SETUP_ACTION_LABEL,
            "action_href": TELEPHONY_SETUP_ACTION_HREF,
        },
    }
