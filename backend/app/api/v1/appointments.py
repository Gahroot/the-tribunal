"""Appointment management endpoints."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.appointment import Appointment
from app.models.workspace import Workspace
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    PaginatedAppointments,
)

router = APIRouter()
logger = structlog.get_logger()


@router.get("", response_model=PaginatedAppointments)
async def list_appointments(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = None,
) -> PaginatedAppointments:
    """List appointments in a workspace.

    Requires workspace membership. All appointments are filtered by workspace_id
    to ensure workspace isolation.
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

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Appointment.scheduled_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    appointments = result.scalars().all()

    log.info("appointments_listed", count=len(appointments), total=total)

    return PaginatedAppointments(
        items=[AppointmentResponse.model_validate(a) for a in appointments],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
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

    # Verify agent exists if provided
    if appointment_in.agent_id:
        from app.models.agent import Agent

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
    return appointment


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
