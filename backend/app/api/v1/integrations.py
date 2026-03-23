"""Integration credential management endpoints."""

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, WorkspaceAccess, WorkspaceAdminAccess
from app.models.workspace import WorkspaceIntegration
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationTestResult,
    IntegrationUpdate,
    IntegrationWithMaskedCredentials,
)

router = APIRouter()
logger = structlog.get_logger()


def mask_api_key(key: str) -> str:
    """Mask an API key for display, showing only last 4 characters."""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


def mask_credentials(credentials: dict[str, Any]) -> dict[str, str]:
    """Mask all sensitive credential values."""
    masked = {}
    for key, value in credentials.items():
        if isinstance(value, str) and value:
            if "key" in key.lower() or "secret" in key.lower() or "token" in key.lower():
                masked[key] = mask_api_key(value)
            elif "email" in key.lower():
                masked[key] = value  # Don't mask emails
            else:
                masked[key] = value if len(value) < 20 else mask_api_key(value)
        elif value is not None:
            masked[key] = str(value)
    return masked


@router.get("", response_model=list[IntegrationWithMaskedCredentials])
async def list_integrations(
    workspace: WorkspaceAccess,
    db: DB,
) -> list[IntegrationWithMaskedCredentials]:
    """List all integrations for a workspace with masked credentials."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
        )
    )
    integrations = result.scalars().all()

    return [
        IntegrationWithMaskedCredentials(
            id=i.id,
            workspace_id=i.workspace_id,
            integration_type=i.integration_type,
            is_active=i.is_active,
            created_at=i.created_at,
            updated_at=i.updated_at,
            masked_credentials=mask_credentials(i.credentials),
        )
        for i in integrations
    ]


@router.get("/{integration_type}", response_model=IntegrationWithMaskedCredentials)
async def get_integration(
    integration_type: str,
    workspace: WorkspaceAccess,
    db: DB,
) -> IntegrationWithMaskedCredentials:
    """Get a specific integration by type."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == integration_type,
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_type}' not found",
        )

    return IntegrationWithMaskedCredentials(
        id=integration.id,
        workspace_id=integration.workspace_id,
        integration_type=integration.integration_type,
        is_active=integration.is_active,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        masked_credentials=mask_credentials(integration.credentials),
    )


@router.post(
    "",
    response_model=IntegrationWithMaskedCredentials,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    integration_data: IntegrationCreate,
    workspace: WorkspaceAdminAccess,
    current_user: CurrentUser,
    db: DB,
) -> IntegrationWithMaskedCredentials:
    """Create a new integration for the workspace."""
    # Check if integration already exists
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == integration_data.integration_type,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{integration_data.integration_type}' already exists. "
            "Use PUT to update.",
        )

    integration = WorkspaceIntegration(
        workspace_id=workspace.id,
        integration_type=integration_data.integration_type,
        credentials=integration_data.credentials,
        is_active=integration_data.is_active,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    logger.info(
        "integration_created",
        workspace_id=str(workspace.id),
        integration_type=integration_data.integration_type,
        user_id=current_user.id,
    )

    return IntegrationWithMaskedCredentials(
        id=integration.id,
        workspace_id=integration.workspace_id,
        integration_type=integration.integration_type,
        is_active=integration.is_active,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        masked_credentials=mask_credentials(integration.credentials),
    )


@router.put("/{integration_type}", response_model=IntegrationWithMaskedCredentials)
async def update_integration(
    integration_type: str,
    integration_data: IntegrationUpdate,
    workspace: WorkspaceAdminAccess,
    current_user: CurrentUser,
    db: DB,
) -> IntegrationWithMaskedCredentials:
    """Update an existing integration's credentials."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == integration_type,
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_type}' not found",
        )

    if integration_data.credentials is not None:
        integration.credentials = integration_data.credentials
    if integration_data.is_active is not None:
        integration.is_active = integration_data.is_active

    await db.commit()
    await db.refresh(integration)

    logger.info(
        "integration_updated",
        workspace_id=str(workspace.id),
        integration_type=integration_type,
        user_id=current_user.id,
    )

    return IntegrationWithMaskedCredentials(
        id=integration.id,
        workspace_id=integration.workspace_id,
        integration_type=integration.integration_type,
        is_active=integration.is_active,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        masked_credentials=mask_credentials(integration.credentials),
    )


@router.delete("/{integration_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_type: str,
    workspace: WorkspaceAdminAccess,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete an integration."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == integration_type,
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_type}' not found",
        )

    await db.delete(integration)
    await db.commit()

    logger.info(
        "integration_deleted",
        workspace_id=str(workspace.id),
        integration_type=integration_type,
        user_id=current_user.id,
    )


async def _test_calcom(client: httpx.AsyncClient, api_key: str) -> IntegrationTestResult:
    """Test Cal.com API connection."""
    response = await client.get(
        "https://api.cal.com/v1/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.status_code == 200:
        try:
            data = response.json()
            user_data = data.get("data", {})
            user_name = user_data.get("name") if isinstance(user_data, dict) else None
            return IntegrationTestResult(
                success=True,
                message="Successfully connected to Cal.com",
                details={"user": user_name},
            )
        except (ValueError, TypeError):
            return IntegrationTestResult(
                success=False,
                message="Cal.com returned invalid JSON response",
            )
    return IntegrationTestResult(
        success=False,
        message=f"Cal.com API returned status {response.status_code}",
    )


async def _test_telnyx(client: httpx.AsyncClient, api_key: str) -> IntegrationTestResult:
    """Test Telnyx API connection."""
    response = await client.get(
        "https://api.telnyx.com/v2/balance",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.status_code == 200:
        try:
            data = response.json()
            balance = data.get("data", {})
            if not isinstance(balance, dict):
                balance = {}
            return IntegrationTestResult(
                success=True,
                message="Successfully connected to Telnyx",
                details={
                    "balance": balance.get("balance"),
                    "currency": balance.get("currency"),
                },
            )
        except (ValueError, TypeError):
            return IntegrationTestResult(
                success=False,
                message="Telnyx returned invalid JSON response",
            )
    return IntegrationTestResult(
        success=False,
        message=f"Telnyx API returned status {response.status_code}",
    )


async def _test_openai(client: httpx.AsyncClient, api_key: str) -> IntegrationTestResult:
    """Test OpenAI API connection."""
    response = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.status_code == 200:
        try:
            data = response.json()
            models_data = data.get("data", [])
            if not isinstance(models_data, list):
                models_data = []
            return IntegrationTestResult(
                success=True,
                message="Successfully connected to OpenAI",
                details={"models_available": len(models_data)},
            )
        except (ValueError, TypeError):
            return IntegrationTestResult(
                success=False,
                message="OpenAI returned invalid JSON response",
            )
    return IntegrationTestResult(
        success=False,
        message=f"OpenAI API returned status {response.status_code}",
    )


async def _test_sendgrid(client: httpx.AsyncClient, api_key: str) -> IntegrationTestResult:
    """Test SendGrid API connection."""
    response = await client.get(
        "https://api.sendgrid.com/v3/user/profile",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.status_code == 200:
        return IntegrationTestResult(
            success=True,
            message="Successfully connected to SendGrid",
        )
    return IntegrationTestResult(
        success=False,
        message=f"SendGrid API returned status {response.status_code}",
    )


# Map integration types to their test functions
_INTEGRATION_TESTERS = {
    "calcom": _test_calcom,
    "telnyx": _test_telnyx,
    "openai": _test_openai,
    "sendgrid": _test_sendgrid,
}


@router.post("/{integration_type}/test", response_model=IntegrationTestResult)
async def test_integration(
    integration_type: str,
    workspace: WorkspaceAccess,
    db: DB,
) -> IntegrationTestResult:
    """Test an integration's connection using stored credentials."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == integration_type,
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_type}' not found",
        )

    tester = _INTEGRATION_TESTERS.get(integration_type)
    if tester is None:
        return IntegrationTestResult(
            success=False,
            message=f"Test not implemented for integration type: {integration_type}",
        )

    credentials = integration.credentials
    api_key = credentials.get("api_key", "")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await tester(client, api_key)
    except httpx.TimeoutException:
        return IntegrationTestResult(
            success=False,
            message="Connection timed out",
        )
    except httpx.RequestError as e:
        return IntegrationTestResult(
            success=False,
            message=f"Connection error: {e!s}",
        )
