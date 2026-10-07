"""Automation management endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.db.scope import apply_workspace_scope
from app.models.automation import Automation
from app.models.automation_execution import AutomationExecution
from app.models.workspace import Workspace
from app.schemas.automation import (
    AutomationConfigIssueSchema,
    AutomationCreate,
    AutomationExecutionSummary,
    AutomationResponse,
    AutomationStatsResponse,
    AutomationUpdate,
    PaginatedAutomations,
)
from app.services.automations.validation import (
    static_config_issues,
    workspace_config_issues,
)

router = APIRouter()


async def _latest_executions(
    db: DB, automation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, AutomationExecution]:
    """Return the most recent execution per automation (one query)."""
    if not automation_ids:
        return {}
    result = await db.execute(
        select(AutomationExecution)
        .where(AutomationExecution.automation_id.in_(automation_ids))
        .order_by(AutomationExecution.automation_id, AutomationExecution.created_at.desc())
        .distinct(AutomationExecution.automation_id)
    )
    return {execution.automation_id: execution for execution in result.scalars().all()}


def _to_response(
    automation: Automation, last_execution: AutomationExecution | None = None
) -> AutomationResponse:
    """Serialize an automation with its readiness and latest run outcome."""
    issues = static_config_issues(
        automation.trigger_type, automation.trigger_config, automation.actions
    )
    response = AutomationResponse.model_validate(automation)
    response.readiness = "incomplete" if issues else "ready"
    response.config_issues = [AutomationConfigIssueSchema(**i.as_dict()) for i in issues]
    response.last_execution = (
        AutomationExecutionSummary.model_validate(last_execution) if last_execution else None
    )
    return response


async def _ensure_activatable(
    db: DB,
    workspace_id: uuid.UUID,
    trigger_type: str,
    trigger_config: dict[str, Any],
    actions: list[dict[str, Any]],
) -> None:
    """Reject activation of an automation the worker cannot execute (422)."""
    issues = static_config_issues(trigger_type, trigger_config, actions)
    if not issues:
        issues = await workspace_config_issues(db, workspace_id, actions)
    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "automation_incomplete",
                "message": (
                    "This automation can't be activated until it's fully set up: "
                    + " ".join(issue.message for issue in issues)
                ),
                "details": {"issues": [issue.as_dict() for issue in issues]},
            },
        )


async def _get_scoped_automation(
    db: DB, workspace_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    result = await db.execute(
        apply_workspace_scope(select(Automation), Automation, workspace_id).where(
            Automation.id == automation_id
        )
    )
    automation = result.scalar_one_or_none()
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation not found",
        )
    return automation


@router.get("/stats", response_model=AutomationStatsResponse)
async def get_automation_stats(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AutomationStatsResponse:
    """Get automation statistics for a workspace."""
    # Total automations
    total_result = await db.execute(
        apply_workspace_scope(
            select(func.count()).select_from(Automation),
            Automation,
            workspace_id,
        )
    )
    total = total_result.scalar_one()

    # Active automations
    active_result = await db.execute(
        apply_workspace_scope(
            select(func.count()).select_from(Automation),
            Automation,
            workspace_id,
        ).where(Automation.is_active.is_(True))
    )
    active = active_result.scalar_one()

    # Triggered today
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    triggered_today_result = await db.execute(
        apply_workspace_scope(
            select(func.count()).select_from(Automation),
            Automation,
            workspace_id,
        ).where(Automation.last_triggered_at >= today_start)
    )
    triggered_today = triggered_today_result.scalar_one()

    return AutomationStatsResponse(
        total=total,
        active=active,
        triggered_today=triggered_today,
    )


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
    query = apply_workspace_scope(select(Automation), Automation, workspace_id)

    if active_only:
        query = query.where(Automation.is_active.is_(True))

    query = query.order_by(Automation.created_at.desc())
    result = await paginate(db, query, page=page, page_size=page_size)
    latest = await _latest_executions(db, [automation.id for automation in result.items])

    return PaginatedAutomations(
        **result.to_dict([_to_response(a, latest.get(a.id)) for a in result.items])
    )


@router.post("", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    workspace_id: uuid.UUID,
    automation_in: AutomationCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AutomationResponse:
    """Create a new automation.

    Inactive automations may be saved as drafts with incomplete configuration;
    an active automation must be fully configured (422 otherwise).
    """
    data = automation_in.model_dump()
    if data["is_active"]:
        await _ensure_activatable(
            db, workspace_id, data["trigger_type"], data["trigger_config"], data["actions"]
        )
    automation = Automation(workspace_id=workspace_id, **data)
    db.add(automation)
    await db.commit()
    await db.refresh(automation)

    return _to_response(automation)


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AutomationResponse:
    """Get an automation by ID."""
    automation = await _get_scoped_automation(db, workspace_id, automation_id)
    latest = await _latest_executions(db, [automation.id])
    return _to_response(automation, latest.get(automation.id))


@router.put("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    automation_in: AutomationUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AutomationResponse:
    """Update an automation.

    Omitted fields keep their stored values. If the automation is (or becomes)
    active, the merged configuration must be complete (422 otherwise).
    """
    automation = await _get_scoped_automation(db, workspace_id, automation_id)

    # ``None`` for a non-nullable field means "unchanged"; only description is
    # nullable and may be cleared explicitly.
    update_data = {
        field: value
        for field, value in automation_in.model_dump(exclude_unset=True).items()
        if value is not None or field == "description"
    }

    is_active = update_data.get("is_active", automation.is_active)
    if is_active:
        await _ensure_activatable(
            db,
            workspace_id,
            update_data.get("trigger_type", automation.trigger_type),
            update_data.get("trigger_config", automation.trigger_config),
            update_data.get("actions", automation.actions),
        )

    for field, value in update_data.items():
        setattr(automation, field, value)

    await db.commit()
    await db.refresh(automation)

    latest = await _latest_executions(db, [automation.id])
    return _to_response(automation, latest.get(automation.id))


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete an automation."""
    automation = await _get_scoped_automation(db, workspace_id, automation_id)
    await db.delete(automation)
    await db.commit()


@router.post("/{automation_id}/toggle", response_model=AutomationResponse)
async def toggle_automation(
    workspace_id: uuid.UUID,
    automation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AutomationResponse:
    """Toggle automation active status. Activation requires a complete setup."""
    automation = await _get_scoped_automation(db, workspace_id, automation_id)

    if not automation.is_active:
        await _ensure_activatable(
            db,
            workspace_id,
            automation.trigger_type,
            automation.trigger_config,
            automation.actions,
        )
    automation.is_active = not automation.is_active
    await db.commit()
    await db.refresh(automation)

    latest = await _latest_executions(db, [automation.id])
    return _to_response(automation, latest.get(automation.id))
