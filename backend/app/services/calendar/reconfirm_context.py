"""Purpose-specific context for appointment reconfirmation voice calls."""

import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.appointment import Appointment
from app.models.conversation import Message
from app.services.idempotency import derive_outbound_key


async def reconfirm_prompt(call_id: str, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> str:
    """Return context only for a call whose key matches this workspace's appointment."""
    async with AsyncSessionLocal() as db:
        call_message = await db.scalar(
            select(Message).where(Message.provider_message_id == call_id)
        )
        if not call_message or not call_message.body.startswith("appointment_reconfirm:"):
            return ""
        try:
            appointment_id = int(call_message.body.partition(":")[2])
        except ValueError:
            return ""
        appointment = await db.scalar(
            select(Appointment).where(
                Appointment.id == appointment_id,
                Appointment.workspace_id == workspace_id,
                Appointment.agent_id == agent_id,
                Appointment.status == "scheduled",
            )
        )
        if not appointment or call_message.idempotency_key != derive_outbound_key(
            "appointment_reconfirm_call", appointment.id, appointment.scheduled_at
        ):
            return ""
        return (
            "\nThis is an appointment reconfirmation call. Confirm whether the contact can "
            f"attend the appointment at {appointment.scheduled_at.isoformat()}. "
            "If they need to reschedule, help them choose a new time. "
            "After they explicitly say yes, use confirm_appointment with their exact words. "
            "Never call it for uncertainty, a voicemail, or a reschedule request. "
            "Do not claim the appointment has been confirmed without their answer."
        )
