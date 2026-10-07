"""Credential storage helpers for realtor onboarding integrations."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_json
from app.db.scope import apply_workspace_scope
from app.models.workspace import WorkspaceIntegration

logger = structlog.get_logger()

CALCOM_INTEGRATION_TYPE = "calcom"
FOLLOWUPBOSS_INTEGRATION_TYPE = "followupboss"


async def upsert_workspace_integration_credentials(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    integration_type: str,
    credentials: dict[str, Any],
) -> WorkspaceIntegration:
    """Create or reactivate a workspace integration with encrypted credentials."""
    result = await db.execute(
        apply_workspace_scope(
            select(WorkspaceIntegration),
            WorkspaceIntegration,
            workspace_id,
        ).where(WorkspaceIntegration.integration_type == integration_type)
    )
    existing = result.scalar_one_or_none()
    encrypted_credentials = encrypt_json(credentials)

    if existing is not None:
        existing.encrypted_credentials = encrypted_credentials
        existing.is_active = True
        return existing

    integration = WorkspaceIntegration(
        workspace_id=workspace_id,
        integration_type=integration_type,
        encrypted_credentials=encrypted_credentials,
        is_active=True,
    )
    db.add(integration)
    return integration


async def store_calcom_credentials(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    api_key: str,
) -> WorkspaceIntegration:
    """Store or update the Cal.com API key for a workspace."""
    return await upsert_workspace_integration_credentials(
        db=db,
        workspace_id=workspace_id,
        integration_type=CALCOM_INTEGRATION_TYPE,
        credentials={"api_key": api_key},
    )


async def store_followupboss_credentials(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    api_key: str,
    account_name: str | None = None,
) -> WorkspaceIntegration:
    """Store or update the Follow Up Boss API key for a workspace.

    ``account_name`` (from FUB ``/me``) is stored alongside the key so the
    connection can be shown as "Connected as …" after a reload without
    re-calling Follow Up Boss.
    """
    credentials: dict[str, Any] = {"api_key": api_key}
    if account_name:
        credentials["account_name"] = account_name
    return await upsert_workspace_integration_credentials(
        db=db,
        workspace_id=workspace_id,
        integration_type=FOLLOWUPBOSS_INTEGRATION_TYPE,
        credentials=credentials,
    )


async def get_workspace_calcom_api_key(
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> str | None:
    """Return the active stored Cal.com API key for a workspace, if present.

    Delegates to the shared calendar credential resolver (no global fallback)
    so onboarding and booking agree on what "connected" means.
    """
    from app.services.calendar.calcom_credentials import (
        CalComCredentialError,
        resolve_calcom_credentials,
    )

    try:
        credentials = await resolve_calcom_credentials(
            db, workspace_id, allow_global_fallback=False
        )
    except CalComCredentialError:
        return None
    return credentials.api_key
