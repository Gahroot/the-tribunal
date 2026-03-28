"""Human nudge management endpoints."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import DB, WorkspaceAccess
from app.db.pagination import paginate
from app.models.human_nudge import HumanNudge
from app.schemas.nudge import (
    NudgeListResponse,
    NudgeResponse,
    NudgeSettingsResponse,
    NudgeSettingsUpdate,
    NudgeSnoozeRequest,
    NudgeStatsResponse,
)

router = APIRouter()


def _nudge_to_response(nudge: HumanNudge) -> NudgeResponse:
    """Convert a HumanNudge model to a NudgeResponse, populating contact fields."""
    contact = nudge.contact
    return NudgeResponse(
        id=nudge.id,
        workspace_id=nudge.workspace_id,
        contact_id=nudge.contact_id,
        nudge_type=nudge.nudge_type,
        title=nudge.title,
        message=nudge.message,
        suggested_action=nudge.suggested_action,
        priority=nudge.priority,
        due_date=nudge.due_date,
        source_date_field=nudge.source_date_field,
        status=nudge.status,
        snoozed_until=nudge.snoozed_until,
        delivered_via=nudge.delivered_via,
        delivered_at=nudge.delivered_at,
        acted_at=nudge.acted_at,
        assigned_to_user_id=nudge.assigned_to_user_id,
        created_at=nudge.created_at,
        contact_name=contact.full_name if contact else None,
        contact_phone=contact.phone_number if contact else None,
        contact_company=contact.company_name if contact else None,
    )


async def _get_nudge_or_404(
    db: DB,
    nudge_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> HumanNudge:
    """Fetch a nudge by ID, ensuring it belongs to the workspace."""
    result = await db.execute(
        select(HumanNudge)
        .options(joinedload(HumanNudge.contact))
        .where(
            HumanNudge.id == nudge_id,
            HumanNudge.workspace_id == workspace_id,
        )
    )
    nudge = result.unique().scalar_one_or_none()
    if not nudge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nudge not found",
        )
    return nudge


@router.get("", response_model=NudgeListResponse)
async def list_nudges(
    workspace: WorkspaceAccess,
    db: DB,
    status_filter: str | None = Query(None, alias="status"),
    nudge_type: str | None = Query(None),
    priority: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> NudgeListResponse:
    """List nudges for a workspace with optional filters.

    Defaults to showing pending and sent nudges, ordered by due_date ascending.
    """
    query = (
        select(HumanNudge)
        .options(joinedload(HumanNudge.contact))
        .where(HumanNudge.workspace_id == workspace.id)
        .order_by(HumanNudge.due_date.asc())
    )

    if status_filter:
        query = query.where(HumanNudge.status == status_filter)
    else:
        # Default: show pending and sent
        query = query.where(HumanNudge.status.in_(["pending", "sent"]))

    if nudge_type:
        query = query.where(HumanNudge.nudge_type == nudge_type)

    if priority:
        query = query.where(HumanNudge.priority == priority)

    result = await paginate(db, query, page=page, page_size=page_size, unique=True)

    return NudgeListResponse(
        items=[_nudge_to_response(n) for n in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/stats", response_model=NudgeStatsResponse)
async def get_nudge_stats(
    workspace: WorkspaceAccess,
    db: DB,
) -> NudgeStatsResponse:
    """Get nudge counts grouped by status."""
    result = await db.execute(
        select(HumanNudge.status, func.count(HumanNudge.id))
        .where(HumanNudge.workspace_id == workspace.id)
        .group_by(HumanNudge.status)
    )
    counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    return NudgeStatsResponse(
        pending=counts.get("pending", 0),
        sent=counts.get("sent", 0),
        acted=counts.get("acted", 0),
        dismissed=counts.get("dismissed", 0),
        snoozed=counts.get("snoozed", 0),
        total=sum(counts.values()),
    )


@router.put("/{nudge_id}/act", response_model=NudgeResponse)
async def act_on_nudge(
    nudge_id: uuid.UUID,
    workspace: WorkspaceAccess,
    db: DB,
) -> NudgeResponse:
    """Mark a nudge as acted upon."""
    nudge = await _get_nudge_or_404(db, nudge_id, workspace.id)

    nudge.status = "acted"
    nudge.acted_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(nudge)

    return _nudge_to_response(nudge)


@router.put("/{nudge_id}/dismiss", response_model=NudgeResponse)
async def dismiss_nudge(
    nudge_id: uuid.UUID,
    workspace: WorkspaceAccess,
    db: DB,
) -> NudgeResponse:
    """Dismiss a nudge."""
    nudge = await _get_nudge_or_404(db, nudge_id, workspace.id)

    nudge.status = "dismissed"

    await db.commit()
    await db.refresh(nudge)

    return _nudge_to_response(nudge)


@router.put("/{nudge_id}/snooze", response_model=NudgeResponse)
async def snooze_nudge(
    nudge_id: uuid.UUID,
    body: NudgeSnoozeRequest,
    workspace: WorkspaceAccess,
    db: DB,
) -> NudgeResponse:
    """Snooze a nudge until a specified time."""
    nudge = await _get_nudge_or_404(db, nudge_id, workspace.id)

    nudge.status = "snoozed"
    nudge.snoozed_until = body.snooze_until

    await db.commit()
    await db.refresh(nudge)

    return _nudge_to_response(nudge)


# ── Nudge Settings (stored in workspace.settings JSONB) ──────────────


settings_router = APIRouter()


@settings_router.get("", response_model=NudgeSettingsResponse)
async def get_nudge_settings(
    workspace: WorkspaceAccess,
) -> NudgeSettingsResponse:
    """Get workspace nudge settings."""
    nudge_settings = workspace.settings.get("nudge_settings", {})
    return NudgeSettingsResponse(**nudge_settings)


@settings_router.put("", response_model=NudgeSettingsResponse)
async def update_nudge_settings(
    update: NudgeSettingsUpdate,
    workspace: WorkspaceAccess,
    db: DB,
) -> NudgeSettingsResponse:
    """Update workspace nudge settings."""
    current_settings = dict(workspace.settings)
    nudge_settings = current_settings.get("nudge_settings", {})

    update_data = update.model_dump(exclude_unset=True)
    nudge_settings.update(update_data)
    current_settings["nudge_settings"] = nudge_settings
    workspace.settings = current_settings

    await db.commit()
    await db.refresh(workspace)

    return NudgeSettingsResponse(**workspace.settings.get("nudge_settings", {}))
