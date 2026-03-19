"""Appointment management endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate_unique
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.workspace import Workspace
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    PaginatedAppointments,
)

# ---------------------------------------------------------------------------
# Stats response schemas
# ---------------------------------------------------------------------------


class AppointmentOverallStats(BaseModel):
    """Overall appointment statistics for the workspace."""

    total: int
    scheduled: int
    completed: int
    no_show: int
    cancelled: int
    show_up_rate: float


class AppointmentAgentStat(BaseModel):
    """Per-agent appointment statistics."""

    agent_id: str
    agent_name: str
    total: int
    completed: int
    no_show: int
    show_up_rate: float


class AppointmentCampaignStat(BaseModel):
    """Per-campaign appointment statistics."""

    campaign_id: str
    campaign_name: str
    total: int
    completed: int
    no_show: int
    show_up_rate: float


class AppointmentStatsResponse(BaseModel):
    """Full show-up rate analytics response."""

    overall: AppointmentOverallStats
    by_agent: list[AppointmentAgentStat]
    by_campaign: list[AppointmentCampaignStat]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calc_show_up_rate(completed: int, no_show: int) -> float:
    """Return show-up rate as a percentage, or 0 when there is no data."""
    denom = completed + no_show
    if denom == 0:
        return 0.0
    return round(completed / denom * 100, 1)


router = APIRouter()
logger = structlog.get_logger()


async def _try_calcom_sync(
    appointment: Appointment,
    contact_email: str | None,
    contact_name: str,
    contact_phone: str | None,
    event_type_id: int,
    db: Any,
    log: Any,
) -> None:
    """Attempt to sync an appointment to Cal.com.

    On success: sets sync_status='synced' and stores booking IDs.
    On failure: logs error and stores it in sync_error; leaves sync_status='pending'.
    Never raises — callers should not fail due to Cal.com sync errors.
    """
    from app.core.config import settings
    from app.services.calendar.calcom import CalComError, CalComService

    if not settings.calcom_api_key:
        log.debug("calcom_sync_skipped_no_api_key")
        return

    if not contact_email:
        log.debug("calcom_sync_skipped_no_email")
        return

    calcom = CalComService(settings.calcom_api_key)
    try:
        booking = await calcom.create_booking(
            event_type_id=event_type_id,
            contact_email=contact_email,
            contact_name=contact_name,
            start_time=appointment.scheduled_at,
            duration_minutes=appointment.duration_minutes,
            phone_number=contact_phone,
            metadata={"crm_appointment_id": appointment.id},
        )

        # Parse response — Cal.com v2 wraps in {"data": {...}}
        booking_data: dict[str, Any] = booking.get("data", booking)

        appointment.calcom_booking_uid = booking_data.get("uid")
        appointment.calcom_booking_id = booking_data.get("id")
        appointment.calcom_event_type_id = event_type_id
        appointment.sync_status = "synced"
        appointment.last_synced_at = datetime.now(UTC)
        appointment.sync_error = None

        await db.commit()
        await db.refresh(appointment)

        log.info(
            "calcom_sync_success",
            appointment_id=appointment.id,
            booking_uid=appointment.calcom_booking_uid,
        )

    except CalComError as exc:
        log.warning("calcom_sync_failed", appointment_id=appointment.id, error=str(exc))
        appointment.sync_error = str(exc)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        log.error(
            "calcom_sync_unexpected_error",
            appointment_id=appointment.id,
            error=str(exc),
        )
        appointment.sync_error = str(exc)
        await db.commit()
    finally:
        await calcom.close()


@router.get("", response_model=PaginatedAppointments)
async def list_appointments(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(
        None, description="Filter by status: scheduled/completed/no_show/cancelled"
    ),
    contact_id: int | None = Query(None),
    agent_id: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> PaginatedAppointments:
    """List appointments in a workspace.

    Requires workspace membership. All appointments are filtered by workspace_id
    to ensure workspace isolation.

    Optional filters:
    - status_filter: filter by appointment status
    - contact_id: filter by contact (indexed)
    - agent_id: filter by agent UUID (indexed)
    - date_from: appointments scheduled on or after this datetime (indexed)
    - date_to: appointments scheduled on or before this datetime (indexed)
    """
    log = logger.bind(
        workspace_id=str(workspace_id),
        user_id=current_user.id,
        endpoint="list_appointments",
    )
    log.info("listing_appointments")

    query = (
        select(Appointment)
        .options(selectinload(Appointment.contact))
        .where(Appointment.workspace_id == workspace_id)
    )

    if status_filter:
        query = query.where(Appointment.status == status_filter)
    if contact_id is not None:
        query = query.where(Appointment.contact_id == contact_id)
    if agent_id is not None:
        query = query.where(Appointment.agent_id == uuid.UUID(agent_id))
    if date_from is not None:
        query = query.where(Appointment.scheduled_at >= date_from)
    if date_to is not None:
        query = query.where(Appointment.scheduled_at <= date_to)

    query = query.order_by(Appointment.scheduled_at.desc())
    result = await paginate_unique(db, query, page=page, page_size=page_size)

    log.info("appointments_listed", count=len(result.items), total=result.total)

    return PaginatedAppointments(
        items=[AppointmentResponse.model_validate(a) for a in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    workspace_id: uuid.UUID,
    appointment_in: AppointmentCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Appointment:
    """Create a new appointment.

    Requires workspace membership. Validates contact and agent exist in workspace.
    Initial sync_status is set to 'pending' for Cal.com sync.
    After saving to DB, immediately attempts Cal.com sync if agent has calcom_event_type_id
    and contact has an email. Sync failures do not fail the request.
    """
    log = logger.bind(
        workspace_id=str(workspace_id),
        contact_id=appointment_in.contact_id,
        user_id=current_user.id,
        endpoint="create_appointment",
    )
    log.info("creating_appointment")

    # Verify contact exists in workspace
    from app.models.contact import Contact

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == appointment_in.contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()

    if not contact:
        log.warning("contact_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Verify agent exists if provided, and stash for sync below
    agent = None
    if appointment_in.agent_id:
        agent_result = await db.execute(
            select(Agent).where(
                Agent.id == uuid.UUID(appointment_in.agent_id),
                Agent.workspace_id == workspace_id,
            )
        )
        agent = agent_result.scalar_one_or_none()

        if not agent:
            log.warning("agent_not_found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

    appointment = Appointment(
        workspace_id=workspace_id,
        **appointment_in.model_dump(),
        agent_id=uuid.UUID(appointment_in.agent_id) if appointment_in.agent_id else None,
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    log.info("appointment_created", appointment_id=appointment.id)

    # Attempt immediate Cal.com sync if agent is configured
    if agent is not None and agent.calcom_event_type_id:
        contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()
        await _try_calcom_sync(
            appointment=appointment,
            contact_email=contact.email,
            contact_name=contact_name,
            contact_phone=contact.phone_number,
            event_type_id=agent.calcom_event_type_id,
            db=db,
            log=log,
        )

    return appointment


@router.post(
    "/{appointment_id}/sync",
    response_model=dict,
    summary="Retry Cal.com sync for a pending appointment",
)
async def sync_appointment(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, Any]:
    """Retry syncing an appointment to Cal.com.

    Loads the appointment and its agent, then attempts to create/update the
    Cal.com booking. Returns the new sync status and booking UID on success,
    or an error message on failure.
    """
    log = logger.bind(
        workspace_id=str(workspace_id),
        appointment_id=appointment_id,
        user_id=current_user.id,
        endpoint="sync_appointment",
    )

    # Load appointment
    appt_result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    appointment = appt_result.scalar_one_or_none()

    if not appointment:
        log.warning("appointment_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Load contact
    from app.models.contact import Contact

    contact_result = await db.execute(
        select(Contact).where(Contact.id == appointment.contact_id)
    )
    contact = contact_result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Resolve event_type_id: prefer appointment's own stored value, fall back to agent
    event_type_id: int | None = appointment.calcom_event_type_id

    if event_type_id is None and appointment.agent_id is not None:
        agent_result = await db.execute(
            select(Agent).where(Agent.id == appointment.agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            event_type_id = agent.calcom_event_type_id

    if not event_type_id:
        return {
            "status": "failed",
            "error": "No Cal.com event type configured for this appointment",
        }

    if not contact.email:
        return {"status": "failed", "error": "Contact has no email address"}

    contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()

    # Reset sync_status to pending before retry so helper can update it
    appointment.sync_status = "pending"
    appointment.sync_error = None

    await _try_calcom_sync(
        appointment=appointment,
        contact_email=contact.email,
        contact_name=contact_name,
        contact_phone=contact.phone_number,
        event_type_id=event_type_id,
        db=db,
        log=log,
    )

    if appointment.sync_status == "synced":
        return {
            "status": "synced",
            "calcom_booking_uid": appointment.calcom_booking_uid,
        }

    return {
        "status": "failed",
        "error": appointment.sync_error or "Unknown error",
    }


@router.get("/stats", response_model=AppointmentStatsResponse)
async def get_appointment_stats(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AppointmentStatsResponse:
    """Return show-up rate analytics for the workspace.

    Computes overall appointment counts by status and derived show-up rate,
    then breaks the same metrics down by agent and by campaign.

    show_up_rate = completed / (completed + no_show) * 100, else 0.
    """
    log = logger.bind(
        workspace_id=str(workspace_id),
        user_id=current_user.id,
        endpoint="get_appointment_stats",
    )
    log.info("fetching_appointment_stats")

    # ------------------------------------------------------------------
    # Overall stats — single aggregation query
    # ------------------------------------------------------------------
    overall_result = await db.execute(
        select(
            func.count(Appointment.id).label("total"),
            func.count(case((Appointment.status == "scheduled", 1))).label("scheduled"),
            func.count(case((Appointment.status == "completed", 1))).label("completed"),
            func.count(case((Appointment.status == "no_show", 1))).label("no_show"),
            func.count(case((Appointment.status == "cancelled", 1))).label("cancelled"),
        ).where(Appointment.workspace_id == workspace_id)
    )
    row = overall_result.one()
    overall = AppointmentOverallStats(
        total=row.total,
        scheduled=row.scheduled,
        completed=row.completed,
        no_show=row.no_show,
        cancelled=row.cancelled,
        show_up_rate=_calc_show_up_rate(row.completed, row.no_show),
    )

    # ------------------------------------------------------------------
    # Per-agent stats — group by agent_id, join Agent for name
    # ------------------------------------------------------------------
    agent_rows_result = await db.execute(
        select(
            Appointment.agent_id,
            Agent.name.label("agent_name"),
            func.count(Appointment.id).label("total"),
            func.count(case((Appointment.status == "completed", 1))).label("completed"),
            func.count(case((Appointment.status == "no_show", 1))).label("no_show"),
        )
        .join(Agent, Appointment.agent_id == Agent.id, isouter=False)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.agent_id.is_not(None),
        )
        .group_by(Appointment.agent_id, Agent.name)
        .order_by(func.count(Appointment.id).desc())
    )
    by_agent: list[AppointmentAgentStat] = [
        AppointmentAgentStat(
            agent_id=str(r.agent_id),
            agent_name=r.agent_name,
            total=r.total,
            completed=r.completed,
            no_show=r.no_show,
            show_up_rate=_calc_show_up_rate(r.completed, r.no_show),
        )
        for r in agent_rows_result.all()
    ]

    # ------------------------------------------------------------------
    # Per-campaign stats — group by campaign_id, join Campaign for name
    # ------------------------------------------------------------------
    campaign_rows_result = await db.execute(
        select(
            Appointment.campaign_id,
            Campaign.name.label("campaign_name"),
            func.count(Appointment.id).label("total"),
            func.count(case((Appointment.status == "completed", 1))).label("completed"),
            func.count(case((Appointment.status == "no_show", 1))).label("no_show"),
        )
        .join(Campaign, Appointment.campaign_id == Campaign.id, isouter=False)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.campaign_id.is_not(None),
        )
        .group_by(Appointment.campaign_id, Campaign.name)
        .order_by(func.count(Appointment.id).desc())
    )
    by_campaign: list[AppointmentCampaignStat] = [
        AppointmentCampaignStat(
            campaign_id=str(r.campaign_id),
            campaign_name=r.campaign_name,
            total=r.total,
            completed=r.completed,
            no_show=r.no_show,
            show_up_rate=_calc_show_up_rate(r.completed, r.no_show),
        )
        for r in campaign_rows_result.all()
    ]

    log.info(
        "appointment_stats_fetched",
        total=overall.total,
        by_agent_count=len(by_agent),
        by_campaign_count=len(by_campaign),
    )
    return AppointmentStatsResponse(overall=overall, by_agent=by_agent, by_campaign=by_campaign)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Appointment:
    """Get an appointment by ID."""
    log = logger.bind(
        workspace_id=str(workspace_id),
        appointment_id=appointment_id,
        endpoint="get_appointment",
    )

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.warning("appointment_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    log.info("appointment_retrieved")
    return appointment


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    workspace_id: uuid.UUID,
    appointment_id: int,
    appointment_in: AppointmentUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Appointment:
    """Update an appointment."""
    log = logger.bind(
        workspace_id=str(workspace_id),
        appointment_id=appointment_id,
        endpoint="update_appointment",
    )

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.warning("appointment_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Update fields
    update_data = appointment_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(appointment, field, value)

    await db.commit()
    await db.refresh(appointment)

    log.info("appointment_updated", status=appointment.status)
    return appointment


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete/cancel an appointment."""
    log = logger.bind(
        workspace_id=str(workspace_id),
        appointment_id=appointment_id,
        endpoint="delete_appointment",
    )

    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    appointment = result.scalar_one_or_none()

    if not appointment:
        log.warning("appointment_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    await db.delete(appointment)
    await db.commit()

    log.info("appointment_deleted")


@router.post(
    "/{appointment_id}/send-reminder",
    response_model=dict,
    summary="Manually send an SMS reminder for a scheduled appointment",
)
async def send_appointment_reminder(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, Any]:
    """Send an immediate SMS reminder for a scheduled appointment.

    Only works for appointments with status='scheduled'.
    Updates reminder_sent_at on success.
    Returns success/failure info without raising on SMS-level errors (opted out,
    no phone, no from number).
    """
    from app.models.contact import Contact
    from app.services.calendar import reminder_service

    log = logger.bind(
        workspace_id=str(workspace_id),
        appointment_id=appointment_id,
        user_id=current_user.id,
        endpoint="send_appointment_reminder",
    )

    # Load and validate appointment
    appt_result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
        )
    )
    appointment = appt_result.scalar_one_or_none()

    if not appointment:
        log.warning("appointment_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reminders can only be sent for scheduled appointments",
        )

    # Load contact
    contact_result = await db.execute(
        select(Contact).where(Contact.id == appointment.contact_id)
    )
    contact = contact_result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Load agent (optional)
    agent = None
    if appointment.agent_id is not None:
        agent_result = await db.execute(
            select(Agent).where(Agent.id == appointment.agent_id)
        )
        agent = agent_result.scalar_one_or_none()

    try:
        result = await reminder_service.send_appointment_reminder(
            db=db,
            appointment=appointment,
            workspace=workspace,
            contact=contact,
            agent=agent,
        )
        log.info("manual_reminder_result", success=result.get("success"))
        return result
    except Exception as exc:
        log.exception("manual_reminder_unexpected_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while sending the reminder",
        ) from exc
