"""Automation management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.models.automation import Automation
from app.models.workspace import Workspace
from app.schemas.automation import (
    AutomationCreate,
    AutomationResponse,
    AutomationUpdate,
    PaginatedAutomations,
)

router = APIRouter()


@router.get("", response_model=PaginatedAutomations)
async def list_automations(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    active_only: bool = False,
) -> PaginatedAutomations:
    """List automations in a workspace."""
    query = select(Automation).where(Automation.workspace_id == workspace_id)

    if active_only:
        query = query.where(Automation.is_active.is_(True))

    query = query.order_by(Automation.created_at.desc())
    result = await paginate(db, query, page=page, page_size=page_size)

    return PaginatedAutomations(
        items=[AutomationResponse.model_validate(a) for a in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.post("", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    workspace_id: uuid.UUID,
    automation_in: AutomationCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Automation:
    """Create a new automation."""
    # Convert actions from pydantic models to dicts
    actions_data = [action.model_dump() for action in automation_in.actions]

    automation = Automation(
        workspace_id=workspace_id,
        name=automation_in.name,
        description=automation_in.description,
        trigger_type=automation_in.trigger_type,
        trigger_config=automation_in.trigger_config,
        actions=actions_data,
        is_active=automation_in.is_active,
    )
    db.add(automation)
    await db.commit()
    await db.refresh(automation)

    return automation


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Automation:
    """Get an automation by ID."""
    result = await db.execute(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.workspace_id == workspace_id,
        )
    )
    automation = result.scalar_one_or_none()

    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )

    return automation


@router.put("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    automation_in: AutomationUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Automation:
    """Update an automation."""
    result = await db.execute(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.workspace_id == workspace_id,
        )
    )
    automation = result.scalar_one_or_none()

    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )

    # Update fields
    update_data = automation_in.model_dump(exclude_unset=True)

    # Handle actions specially to convert pydantic models to dicts
    if "actions" in update_data and update_data["actions"] is not None:
        update_data["actions"] = [
            action.model_dump() if hasattr(action, "model_dump") else action
            for action in update_data["actions"]
        ]

    for field, value in update_data.items():
        setattr(automation, field, value)

    await db.commit()
    await db.refresh(automation)

    return automation


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete an automation."""
    result = await db.execute(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.workspace_id == workspace_id,
        )
    )
    automation = result.scalar_one_or_none()

    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )

    await db.delete(automation)
    await db.commit()


@router.post("/{automation_id}/toggle", response_model=AutomationResponse)
async def toggle_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Automation:
    """Toggle automation active status."""
    result = await db.execute(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.workspace_id == workspace_id,
        )
    )
    automation = result.scalar_one_or_none()

    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )

    automation.is_active = not automation.is_active
    await db.commit()
    await db.refresh(automation)

    return automation
