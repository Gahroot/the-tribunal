"""Appointment business logic service."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.pagination import paginate
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.schemas.appointment import (
    AppointmentAgentStat,
    AppointmentCampaignStat,
    AppointmentCreate,
    AppointmentOverallStats,
    AppointmentResponse,
    AppointmentStatsResponse,
    AppointmentUpdate,
    PaginatedAppointments,
)

logger = structlog.get_logger()


def _calc_show_up_rate(completed: int, no_show: int) -> float:
    """Return show-up rate as a percentage, or 0 when there is no data."""
    denom = completed + no_show
    if denom == 0:
        return 0.0
    return round(completed / denom * 100, 1)


class AppointmentService:
    """Service for appointment CRUD, stats, and Cal.com sync."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.log = logger.bind(component="appointment_service")

    async def list_appointments(
        self,
        workspace_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
        contact_id: int | None = None,
        agent_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> PaginatedAppointments:
        """List appointments with optional filters."""
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
        result = await paginate(self.db, query, page=page, page_size=page_size, unique=True)

        return PaginatedAppointments(**result.to_response(AppointmentResponse))

    async def create_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_in: AppointmentCreate,
    ) -> Appointment:
        """Create a new appointment, with immediate Cal.com sync if configured."""
        log = self.log.bind(workspace_id=str(workspace_id), contact_id=appointment_in.contact_id)

        # Verify contact exists in workspace
        contact_result = await self.db.execute(
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
        agent = None
        if appointment_in.agent_id:
            agent_result = await self.db.execute(
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
            agent_id=uuid.UUID(appointment_in.agent_id) if appointment_in.agent_id else None,
            **appointment_in.model_dump(exclude={"agent_id"}),
        )
        self.db.add(appointment)
        await self.db.commit()
        await self.db.refresh(appointment)

        log.info("appointment_created", appointment_id=appointment.id)

        # Attempt immediate Cal.com sync if agent is configured
        if agent is not None and agent.calcom_event_type_id:
            contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()
            await self._try_calcom_sync(
                appointment=appointment,
                contact_email=contact.email,
                contact_name=contact_name,
                contact_phone=contact.phone_number,
                event_type_id=agent.calcom_event_type_id,
            )

        return appointment

    async def get_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
    ) -> Appointment:
        """Get an appointment by ID, raising 404 if not found."""
        result = await self.db.execute(
            select(Appointment).where(
                Appointment.id == appointment_id,
                Appointment.workspace_id == workspace_id,
            )
        )
        appointment = result.scalar_one_or_none()
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )
        return appointment

    async def update_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
        appointment_in: AppointmentUpdate,
    ) -> Appointment:
        """Update an appointment's fields."""
        appointment = await self.get_appointment(workspace_id, appointment_id)

        update_data = appointment_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(appointment, field, value)

        await self.db.commit()
        await self.db.refresh(appointment)

        self.log.info(
            "appointment_updated",
            workspace_id=str(workspace_id),
            appointment_id=appointment_id,
            status=appointment.status,
        )
        return appointment

    async def delete_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
    ) -> None:
        """Delete an appointment."""
        appointment = await self.get_appointment(workspace_id, appointment_id)
        await self.db.delete(appointment)
        await self.db.commit()
        self.log.info(
            "appointment_deleted",
            workspace_id=str(workspace_id),
            appointment_id=appointment_id,
        )

    async def get_stats(self, workspace_id: uuid.UUID) -> AppointmentStatsResponse:
        """Return show-up rate analytics (overall, by agent, by campaign)."""
        overall_result = await self.db.execute(
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

        agent_rows_result = await self.db.execute(
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

        campaign_rows_result = await self.db.execute(
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

        return AppointmentStatsResponse(
            overall=overall,
            by_agent=by_agent,
            by_campaign=by_campaign,
        )

    async def sync_to_calcom(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
    ) -> dict[str, Any]:
        """Retry Cal.com sync for an appointment. Returns status/result dict."""
        appointment = await self.get_appointment(workspace_id, appointment_id)

        contact_result = await self.db.execute(
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
            agent_result = await self.db.execute(
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

        # Reset sync_status to pending before retry
        appointment.sync_status = "pending"
        appointment.sync_error = None

        await self._try_calcom_sync(
            appointment=appointment,
            contact_email=contact.email,
            contact_name=contact_name,
            contact_phone=contact.phone_number,
            event_type_id=event_type_id,
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

    async def send_reminder(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
        workspace: Workspace,
    ) -> dict[str, Any]:
        """Send an SMS reminder for a scheduled appointment."""
        from app.services.calendar import reminder_service

        appointment = await self.get_appointment(workspace_id, appointment_id)

        if appointment.status != "scheduled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reminders can only be sent for scheduled appointments",
            )

        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == appointment.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found",
            )

        agent = None
        if appointment.agent_id is not None:
            agent_result = await self.db.execute(
                select(Agent).where(Agent.id == appointment.agent_id)
            )
            agent = agent_result.scalar_one_or_none()

        return await reminder_service.send_appointment_reminder(
            db=self.db,
            appointment=appointment,
            workspace=workspace,
            contact=contact,
            agent=agent,
        )

    async def _try_calcom_sync(
        self,
        appointment: Appointment,
        contact_email: str | None,
        contact_name: str,
        contact_phone: str | None,
        event_type_id: int,
    ) -> None:
        """Attempt to sync an appointment to Cal.com.

        On success: sets sync_status='synced' and stores booking IDs.
        On failure: logs error and stores it in sync_error; leaves sync_status='pending'.
        Never raises.
        """
        from app.core.config import settings
        from app.services.calendar.calcom import CalComError, CalComService

        if not settings.calcom_api_key:
            self.log.debug("calcom_sync_skipped_no_api_key")
            return

        if not contact_email:
            self.log.debug("calcom_sync_skipped_no_email")
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

            booking_data: dict[str, Any] = booking.get("data", booking)
            appointment.calcom_booking_uid = booking_data.get("uid")
            appointment.calcom_booking_id = booking_data.get("id")
            appointment.calcom_event_type_id = event_type_id
            appointment.sync_status = "synced"
            appointment.last_synced_at = datetime.now(UTC)
            appointment.sync_error = None

            await self.db.commit()
            await self.db.refresh(appointment)

            self.log.info(
                "calcom_sync_success",
                appointment_id=appointment.id,
                booking_uid=appointment.calcom_booking_uid,
            )

        except CalComError as exc:
            self.log.warning("calcom_sync_failed", appointment_id=appointment.id, error=str(exc))
            appointment.sync_error = str(exc)
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            self.log.error(
                "calcom_sync_unexpected_error",
                appointment_id=appointment.id,
                error=str(exc),
            )
            appointment.sync_error = str(exc)
            await self.db.commit()
        finally:
            await calcom.close()
