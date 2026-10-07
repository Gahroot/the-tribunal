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
from app.models.appointment import Appointment, AppointmentStatus
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.schemas.appointment import (
    AppointmentAgentStat,
    AppointmentCampaignStat,
    AppointmentCancelResponse,
    AppointmentCreate,
    AppointmentOverallStats,
    AppointmentResponse,
    AppointmentStatsResponse,
    AppointmentUpdate,
    CancelProviderResult,
    PaginatedAppointments,
)
from app.services.tags import TagService

logger = structlog.get_logger()

# sync_status for a CRM-cancelled appointment whose external booking was
# intentionally left active (crm_only). A later cancel retries the provider.
SYNC_STATUS_LOCAL_ONLY = "local_only"

_CANCEL_MESSAGES: dict[str, str] = {
    "cancelled": (
        "Cancelled in the CRM and on Cal.com. Cal.com sends its own cancellation "
        "notice to attendees per your Cal.com event settings; the CRM sent no message."
    ),
    "already_cancelled": (
        "Cancelled in the CRM. The Cal.com booking was already cancelled, so Cal.com "
        "sent no new notice and the CRM sent no message."
    ),
    "not_found": (
        "Cancelled in the CRM. Cal.com has no matching booking (it may have been "
        "deleted), so no one was notified."
    ),
    "skipped": (
        "Marked cancelled in the CRM only. The Cal.com booking is still active and "
        "the contact was not notified. Retry the Cal.com cancellation or cancel it in Cal.com."
    ),
    "not_applicable": (
        "Cancelled in the CRM. This appointment has no external calendar booking, "
        "and the contact was not notified."
    ),
}


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
        if agent is not None:
            from app.services.payments.booking_deposit import assign_deposit

            assign_deposit(appointment, agent.booking_deposit_mode)
        self.db.add(appointment)
        await self.db.flush()
        from app.services.opportunities.appointment_stages import move_appointment_opportunities

        await move_appointment_opportunities(self.db, workspace_id, contact.id, "scheduled")
        await TagService(self.db).add_tag_to_contact(
            workspace_id=workspace_id, contact_id=contact.id, name="appointment-scheduled"
        )
        contact.last_appointment_status = "scheduled"
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

        if appointment.deposit_status == "pending" and appointment.sync_status == "synced":
            from app.services.payments.booking_deposit import (
                deliver_deposit_link,
                offer_deposit_checkout,
            )

            had_checkout = bool(appointment.deposit_checkout_session_id)
            await offer_deposit_checkout(self.db, appointment, contact.email)
            await deliver_deposit_link(
                self.db,
                appointment,
                contact,
                agent,
                newly_created=not had_checkout and bool(appointment.deposit_checkout_session_id),
            )
        return appointment

    async def get_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
    ) -> Appointment:
        """Get an appointment by ID, raising 404 if not found.

        Eager-loads ``contact`` so ``AppointmentResponse`` can serialize the
        nested contact summary without triggering an async lazy-load (which
        raises ``MissingGreenlet``) after the request session has committed.
        """
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.contact))
            .where(
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

        previous_status = appointment.status
        update_data = appointment_in.model_dump(exclude_unset=True)
        if (
            update_data.get("status") == AppointmentStatus.CANCELLED
            and previous_status == AppointmentStatus.SCHEDULED
        ):
            # Never report a cancellation while the external booking stays
            # live: route through the provider-first cancel flow. Other field
            # edits commit atomically with it (or roll back with a failure).
            # Re-labelling a completed/no-show record stays a status-only edit.
            update_data.pop("status")
            for field, value in update_data.items():
                setattr(appointment, field, value)
            await self.cancel_appointment(workspace_id, appointment_id)
            return await self.get_appointment(workspace_id, appointment_id)

        for field, value in update_data.items():
            setattr(appointment, field, value)

        if previous_status != appointment.status:
            if appointment.status in (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW):
                from app.services.appointments.show_rate import record_appointment_outcome

                await record_appointment_outcome(self.db, appointment)
            elif appointment.status == AppointmentStatus.SCHEDULED:
                from app.services.opportunities.appointment_stages import (
                    move_appointment_opportunities,
                )

                await move_appointment_opportunities(
                    self.db, workspace_id, appointment.contact_id, "scheduled"
                )
                contact = await self.db.scalar(
                    select(Contact).where(
                        Contact.id == appointment.contact_id,
                        Contact.workspace_id == workspace_id,
                    )
                )
                if contact is not None:
                    contact.last_appointment_status = "scheduled"
                    await TagService(self.db).add_tag_to_contact(
                        workspace_id=workspace_id,
                        contact_id=contact.id,
                        name="appointment-scheduled",
                    )

        await self.db.commit()
        await self.db.refresh(appointment)

        if (
            previous_status != appointment.status
            and appointment.status == AppointmentStatus.NO_SHOW
            and appointment.confirmed_at
        ):
            try:
                from app.services.appointments.waitlist import offer_waitlist_opening

                await offer_waitlist_opening(self.db, appointment)
            except Exception:
                self.log.exception("waitlist_offer_failed", appointment_id=appointment.id)
                await self.db.rollback()

        self.log.info(
            "appointment_updated",
            workspace_id=str(workspace_id),
            appointment_id=appointment_id,
            status=appointment.status,
        )

        # When an operator marks a job completed, enqueue a review request.
        # No-ops unless the workspace enabled the reputation engine + auto
        # trigger. Never let a reputation hiccup fail the appointment update.
        if (
            previous_status != AppointmentStatus.COMPLETED
            and appointment.status == AppointmentStatus.COMPLETED
        ):
            try:
                from tribunal_reviews import ReviewService

                await ReviewService(self.db).enqueue_for_appointment(appointment)
            except Exception as exc:  # noqa: BLE001 — reputation is best-effort
                self.log.warning("review_request_enqueue_failed", error=str(exc))

        return appointment

    async def cancel_appointment(
        self,
        workspace_id: uuid.UUID,
        appointment_id: int,
        *,
        reason: str | None = None,
        crm_only: bool = False,
    ) -> AppointmentCancelResponse:
        """Cancel an appointment, cancelling its Cal.com booking first.

        The row is locked (``FOR UPDATE``) for the whole flow so a repeat
        click or the Cal.com ``BOOKING_CANCELLED`` webhook (which locks the
        same row) serializes behind it instead of double-processing.

        Raises:
            HTTPException 409: appointment is completed / no-show.
            HTTPException 502 ``calendar_cancel_failed``: the provider could
                not cancel the booking; nothing was changed locally.
        """
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.contact))
            .where(
                Appointment.id == appointment_id,
                Appointment.workspace_id == workspace_id,
            )
            .with_for_update(of=Appointment)
            .execution_options(populate_existing=True)
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found"
            )

        reason = (reason or "").strip() or None
        booking_uid = appointment.calcom_booking_uid
        log = self.log.bind(appointment_id=appointment_id, workspace_id=str(workspace_id))

        if appointment.status == AppointmentStatus.CANCELLED:
            pending_external = (
                bool(booking_uid) and appointment.sync_status == SYNC_STATUS_LOCAL_ONLY
            )
            if crm_only or not pending_external:
                # Repeat cancel: nothing left to do, no provider call.
                log.info("appointment_cancel_noop_already_cancelled")
                response = AppointmentCancelResponse(
                    appointment=AppointmentResponse.model_validate(appointment),
                    outcome="already_cancelled",
                    provider="calcom" if booking_uid else "none",
                    provider_result="skipped"
                    if pending_external
                    else ("already_cancelled" if booking_uid else "not_applicable"),
                    attendee_notice="none",
                    message="This appointment was already cancelled. Nothing changed."
                    + (" " + _CANCEL_MESSAGES["skipped"] if pending_external else ""),
                )
                await self.db.rollback()  # release the row lock
                return response
        elif appointment.status != AppointmentStatus.SCHEDULED:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {appointment.status} appointment cannot be cancelled.",
            )

        was_cancelled = appointment.status == AppointmentStatus.CANCELLED
        provider_result: CancelProviderResult
        if not booking_uid:
            provider_result = "not_applicable"
        elif crm_only:
            provider_result = "skipped"
        else:
            provider_result = await self._cancel_calcom_booking(
                appointment,
                reason or appointment.cancellation_reason,
                crm_already_cancelled=was_cancelled,
            )

        now = datetime.now(UTC)
        appointment.status = AppointmentStatus.CANCELLED
        if reason:
            appointment.cancellation_reason = reason
        if provider_result == "skipped":
            appointment.sync_status = SYNC_STATUS_LOCAL_ONLY
        elif booking_uid:
            appointment.sync_status = "synced"
            appointment.last_synced_at = now
            appointment.sync_error = None

        if not was_cancelled:
            contact = appointment.contact
            if contact is not None:
                contact.last_appointment_status = "cancelled"
                await TagService(self.db).add_tag_to_contact(
                    workspace_id=workspace_id,
                    contact_id=contact.id,
                    name="appointment-cancelled",
                )

        await self.db.commit()
        appointment = await self.get_appointment(workspace_id, appointment_id)
        log.info("appointment_cancelled", provider_result=provider_result)

        return AppointmentCancelResponse(
            appointment=AppointmentResponse.model_validate(appointment),
            outcome="cancelled",
            provider="calcom" if booking_uid else "none",
            provider_result=provider_result,
            attendee_notice="provider" if provider_result == "cancelled" else "none",
            message=_CANCEL_MESSAGES[provider_result],
        )

    async def _cancel_calcom_booking(
        self,
        appointment: Appointment,
        reason: str | None,
        *,
        crm_already_cancelled: bool,
    ) -> CancelProviderResult:
        """Cancel the Cal.com booking; map idempotent outcomes, raise on failure."""
        from app.services.calendar.calcom import (
            CalComBookingAlreadyCancelledError,
            CalComError,
            CalComNotFoundError,
            CalComService,
        )
        from app.services.calendar.calcom_credentials import (
            CalComCredentialError,
            resolve_calcom_credentials,
        )

        booking_uid = appointment.calcom_booking_uid or ""
        log = self.log.bind(appointment_id=appointment.id, booking_uid=booking_uid)

        def _fail(message: str, *, retryable: bool, error_code: str) -> HTTPException:
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "calendar_cancel_failed",
                    "message": message,
                    "details": {
                        "provider": "calcom",
                        "retryable": retryable,
                        "error_code": error_code,
                        "crm_only_available": True,
                    },
                },
            )

        try:
            credentials = await resolve_calcom_credentials(self.db, appointment.workspace_id)
        except CalComCredentialError as exc:
            await self.db.rollback()
            log.warning("calcom_cancel_no_credentials", error_code=exc.code)
            raise _fail(
                f"Could not cancel the Cal.com booking: {exc.message} Nothing was changed.",
                retryable=False,
                error_code=exc.code,
            ) from exc

        calcom = CalComService(credentials.api_key)
        try:
            await calcom.cancel_booking(booking_uid, reason=reason or "Cancelled by the business")
            return "cancelled"
        except CalComBookingAlreadyCancelledError:
            return "already_cancelled"
        except CalComNotFoundError:
            log.warning("calcom_cancel_booking_not_found")
            return "not_found"
        except CalComError as exc:
            await self.db.rollback()
            log.warning("calcom_cancel_failed", error=str(exc))
            state = (
                "The appointment stays cancelled in the CRM only and the Cal.com booking is "
                "still active. Try again, or cancel it in Cal.com yourself."
                if crm_already_cancelled
                else "The appointment is still scheduled in the CRM and on Cal.com. Try "
                "again, or mark it cancelled in the CRM only and cancel it in Cal.com yourself."
            )
            raise _fail(
                f"Cal.com could not cancel the booking. {state}",
                retryable=True,
                error_code=type(exc).__name__,
            ) from exc
        finally:
            await calcom.close()

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

        # A synced booking may need only a Checkout retry. Never create another
        # Cal.com booking just to recover its missing deposit link.
        already_synced = appointment.sync_status == "synced" and bool(
            appointment.calcom_booking_uid
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

        if not already_synced:
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
            if appointment.deposit_status == "pending":
                from app.services.payments.booking_deposit import (
                    deliver_deposit_link,
                    offer_deposit_checkout,
                )

                had_checkout = bool(appointment.deposit_checkout_session_id)
                await offer_deposit_checkout(self.db, appointment, contact.email)
                agent = None
                if appointment.agent_id is not None:
                    agent_result = await self.db.execute(
                        select(Agent).where(
                            Agent.id == appointment.agent_id,
                            Agent.workspace_id == workspace_id,
                        )
                    )
                    agent = agent_result.scalar_one_or_none()
                await deliver_deposit_link(
                    self.db,
                    appointment,
                    contact,
                    agent,
                    newly_created=not had_checkout
                    and bool(appointment.deposit_checkout_session_id),
                )
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
        from app.services.calendar.calcom import CalComError, CalComService
        from app.services.calendar.calcom_credentials import (
            CalComCredentialError,
            resolve_calcom_credentials,
        )

        if not contact_email:
            self.log.debug("calcom_sync_skipped_no_email")
            return

        try:
            credentials = await resolve_calcom_credentials(self.db, appointment.workspace_id)
        except CalComCredentialError as exc:
            self.log.debug("calcom_sync_skipped_no_credentials", error_code=exc.code)
            appointment.sync_error = exc.message
            await self.db.commit()
            return

        calcom = CalComService(credentials.api_key)
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
