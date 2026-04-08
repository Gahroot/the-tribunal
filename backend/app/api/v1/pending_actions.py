"""Pending action management endpoints for HITL approval gate."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.models.pending_action import PendingAction
from app.models.workspace import Workspace
from app.schemas.pending_action import (
    ApproveActionRequest,
    PendingActionListResponse,
    PendingActionResponse,
    RejectActionRequest,
)
from app.services.approval.approval_gate_service import approval_gate_service

router = APIRouter()


def _action_to_response(action: PendingAction) -> PendingActionResponse:
    """Convert a PendingAction model to a PendingActionResponse."""
    return PendingActionResponse(
        id=action.id,
        workspace_id=action.workspace_id,
        agent_id=action.agent_id,
        action_type=action.action_type,
        action_payload=action.action_payload,
        description=action.description,
        context=action.context,
        status=action.status,
        urgency=action.urgency,
        reviewed_by_id=action.reviewed_by_id,
        reviewed_at=action.reviewed_at.isoformat() if action.reviewed_at else None,
        review_channel=action.review_channel,
        rejection_reason=action.rejection_reason,
        executed_at=action.executed_at.isoformat() if action.executed_at else None,
        execution_result=action.execution_result,
        expires_at=action.expires_at.isoformat() if action.expires_at else None,
        notification_sent=action.notification_sent,
        notification_sent_at=action.notification_sent_at.isoformat()
        if action.notification_sent_at
        else None,
        created_at=action.created_at.isoformat(),
        updated_at=action.updated_at.isoformat(),
    )


@router.get("/stats")
async def get_stats(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Get pending action counts grouped by status."""
    result = await db.execute(
        select(PendingAction.status, func.count(PendingAction.id))
        .where(PendingAction.workspace_id == workspace_id)
        .group_by(PendingAction.status)
    )
    counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "expired": counts.get("expired", 0),
        "executed": counts.get("executed", 0),
    }


@router.get("", response_model=PendingActionListResponse)
async def list_actions(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    status_filter: str | None = Query(None, alias="status"),
    agent_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PendingActionListResponse:
    """List pending actions for a workspace with optional filters."""
    query = (
        select(PendingAction)
        .where(PendingAction.workspace_id == workspace_id)
        .order_by(PendingAction.created_at.desc())
    )

    if status_filter:
        query = query.where(PendingAction.status == status_filter)

    if agent_id:
        query = query.where(PendingAction.agent_id == agent_id)

    result = await paginate(db, query, page=page, page_size=page_size)

    return PendingActionListResponse(
        items=[_action_to_response(a) for a in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.get("/{action_id}", response_model=PendingActionResponse)
async def get_action(
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PendingActionResponse:
    """Get a specific pending action."""
    result = await db.execute(
        select(PendingAction).where(
            PendingAction.id == action_id,
            PendingAction.workspace_id == workspace_id,
        )
    )
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending action not found",
        )

    return _action_to_response(action)


@router.post("/{action_id}/approve", response_model=PendingActionResponse)
async def approve_action(
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    body: ApproveActionRequest | None = None,
) -> PendingActionResponse:
    """Approve a pending action for execution."""
    # Verify action belongs to workspace
    result = await db.execute(
        select(PendingAction).where(
            PendingAction.id == action_id,
            PendingAction.workspace_id == workspace_id,
        )
    )
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending action not found",
        )

    if action.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action is already {action.status}",
        )

    updated = await approval_gate_service.approve_action(
        db=db,
        action_id=action_id,
        user_id=current_user.id,
    )

    return _action_to_response(updated)


@router.post("/{action_id}/reject", response_model=PendingActionResponse)
async def reject_action(
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    body: RejectActionRequest | None = None,
) -> PendingActionResponse:
    """Reject a pending action."""
    # Verify action belongs to workspace
    result = await db.execute(
        select(PendingAction).where(
            PendingAction.id == action_id,
            PendingAction.workspace_id == workspace_id,
        )
    )
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending action not found",
        )

    if action.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action is already {action.status}",
        )

    updated = await approval_gate_service.reject_action(
        db=db,
        action_id=action_id,
        user_id=current_user.id,
        reason=body.reason if body else None,
    )

    return _action_to_response(updated)
