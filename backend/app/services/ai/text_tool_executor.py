"""Text agent tool execution service.

This module handles tool execution for text/SMS conversations, providing
Cal.com booking integration similar to VoiceToolExecutor but optimized
for the text channel's database-centric workflow.

Key differences from VoiceToolExecutor:
- Uses Conversation and AsyncSession for state management
- Creates Appointment records in database
- Updates Contact email when provided during booking

Usage:
    executor = TextToolExecutor(
        agent=agent,
        conversation=conversation,
        db=db,
        timezone="America/New_York",
    )
    result = await executor.execute("book_appointment", {"date": "2024-01-15", ...})
"""

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from openai.types.chat import ChatCompletionMessageToolCall
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services.ai.base_tool_executor import BaseToolExecutor

logger = structlog.get_logger()


class TextToolExecutor(BaseToolExecutor):
    """Executes tool calls for text/SMS conversations.

    Handles Cal.com booking operations with database persistence,
    contact email updates, and appointment record creation.

    Attributes:
        agent: Agent model with Cal.com configuration
        conversation: Conversation model for context
        db: Async database session
        timezone: Timezone for date handling
    """

    def __init__(
        self,
        agent: Agent,
        conversation: Conversation,
        db: AsyncSession,
        timezone: str = "America/New_York",
    ) -> None:
        super().__init__(agent=agent, timezone=timezone)
        self.conversation = conversation
        self.db = db
        self._contact: Contact | None = None
        self.log = logger.bind(
            service="text_tool_executor",
            agent_id=str(agent.id),
            conversation_id=str(conversation.id),
        )

    # ── OpenAI tool call handling ───────────────────────────────────

    async def handle_tool_calls(
        self,
        tool_calls: list[ChatCompletionMessageToolCall],
    ) -> list[dict[str, Any]]:
        """Handle tool calls from OpenAI and return results."""
        results = []

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            self.log.info(
                "executing_tool_call",
                tool_call_id=tool_call.id,
                function_name=function_name,
                arguments=arguments,
            )

            result = await self.execute(function_name, arguments)

            results.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": json.dumps(result),
            })

            self.log.info(
                "tool_call_completed",
                tool_call_id=tool_call.id,
                success=result.get("success", False),
            )

        return results

    # ── Main dispatch ───────────────────────────────────────────────

    async def execute(
        self,
        function_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call."""
        if function_name == "book_appointment":
            return await self._execute_book_with_contact_lookup(
                date_str=arguments.get("date", ""),
                time_str=arguments.get("time", ""),
                email=arguments.get("email"),
                duration_minutes=arguments.get("duration_minutes", 30),
                notes=arguments.get("notes"),
            )
        if function_name == "check_availability":
            try:
                return await self.execute_check_availability(
                    start_date_str=arguments.get("start_date", ""),
                    end_date_str=arguments.get("end_date"),
                )
            except Exception as e:
                self.log.exception("availability_check_failed", error=str(e))
                return {
                    "success": False,
                    "error": f"Failed to check availability: {e!s}",
                }

        self.log.warning("unknown_text_tool", function_name=function_name)
        return {"success": False, "error": f"Unknown function: {function_name}"}

    # ── Text-only booking wrapper ───────────────────────────────────

    async def _execute_book_with_contact_lookup(
        self,
        date_str: str,
        time_str: str,
        email: str | None = None,
        duration_minutes: int = 30,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Resolve contact, validate datetime, then delegate to base booking."""
        # Check config early (before contact lookup)
        error = self._validate_calcom_config()
        if error:
            return error

        # Get contact info
        contact = await self._get_contact()
        if not contact:
            return {
                "success": False,
                "error": "Contact not found for this conversation",
            }
        self._contact = contact

        # Use provided email or fall back to contact's existing email
        booking_email = email or contact.email

        # If email was provided and contact doesn't have one, update the contact
        if email and not contact.email:
            contact.email = email
            await self.db.flush()
            self.log.info("contact_email_updated", contact_id=contact.id, email=email)

        if not booking_email:
            self.log.warning(
                "contact_email_missing",
                contact_id=contact.id,
                contact_name=contact.full_name,
            )
            return {
                "success": False,
                "error": "Email is required for booking. Please ask for their email.",
            }

        # Parse date and time for the Appointment record
        try:
            tz = self._get_timezone()
            self._appointment_datetime = datetime.strptime(
                f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=tz)
        except ValueError as e:
            self.log.warning("invalid_datetime", error=str(e))
            return {
                "success": False,
                "error": f"Invalid date/time format: {e}",
            }

        # Store duration/notes for post_booking_success hook
        self._pending_duration = duration_minutes
        self._pending_notes = notes

        try:
            return await self.execute_book_appointment(
                date_str=date_str,
                time_str=time_str,
                email=booking_email,
                duration_minutes=duration_minutes,
                notes=notes,
            )
        except Exception as e:
            self.log.exception("booking_failed", error=str(e))
            return {
                "success": False,
                "error": f"Failed to create booking: {e!s}",
            }

    # ── Hook overrides ──────────────────────────────────────────────

    def get_contact_name(self) -> str:
        if self._contact:
            return self._contact.full_name or "Customer"
        return "Customer"

    def get_contact_phone(self) -> str | None:
        if self._contact:
            return self._clean_phone_number(self._contact.phone_number)
        return None

    def get_booking_metadata(self, notes: str | None) -> dict[str, Any] | None:
        return {
            "source": "ai_text_agent",
            "agent_id": str(self.agent.id),
            "conversation_id": str(self.conversation.id),
        }

    def format_availability_result(
        self,
        slots: list[Any],
        start_date_str: str,
        end_date_str: str | None,
    ) -> dict[str, Any]:
        """Format slots for text response with full weekday format."""
        self.log.info("availability_checked", slot_count=len(slots))

        formatted_slots = []
        for slot in slots:
            if slot.date and slot.time:
                try:
                    slot_dt = datetime.strptime(
                        f"{slot.date} {slot.time}", "%Y-%m-%d %H:%M"
                    )
                    formatted = slot_dt.strftime("%A %b %d at %I:%M %p")
                    formatted_slots.append(formatted)
                except ValueError:
                    formatted_slots.append(f"{slot.date} {slot.time}")
            elif slot.time:
                formatted_slots.append(slot.time)

        if not formatted_slots and slots:
            self.log.warning(
                "slot_formatting_fallback",
                raw_slots=[
                    {"date": s.date, "time": s.time}
                    for s in slots[:5]
                ],
            )
            formatted_slots = [
                f"{s.date} {s.time}" for s in slots[:10]
            ]

        return {
            "success": True,
            "available_slots": formatted_slots,
            "slot_count": len(slots),
            "date_range": f"{start_date_str} to {end_date_str or start_date_str}",
        }

    def format_booking_success(
        self,
        result: Any,
        contact_name: str,
        date_str: str,
        time_str: str,
        email: str,
        duration_minutes: int,
    ) -> dict[str, Any]:
        formatted_time = self._appointment_datetime.strftime("%A, %B %d at %I:%M %p")
        return {
            "success": True,
            "booking_uid": result.booking_uid,
            "scheduled_at": self._appointment_datetime.isoformat(),
            "duration_minutes": duration_minutes,
            "message": f"Appointment booked for {formatted_time}",
        }

    async def post_booking_success(
        self,
        result: Any,
        date_str: str,
        time_str: str,
        email: str,
        duration_minutes: int,
        notes: str | None,
    ) -> None:
        """Create Appointment record in database after successful booking."""
        self.log.info(
            "calcom_booking_created",
            booking_uid=result.booking_uid,
            booking_id=result.booking_id,
        )

        contact = self._contact
        assert contact is not None

        appointment = Appointment(
            workspace_id=self.conversation.workspace_id,
            contact_id=contact.id,
            agent_id=self.agent.id,
            scheduled_at=self._appointment_datetime,
            duration_minutes=duration_minutes,
            status="scheduled",
            service_type="video_call",
            notes=notes,
            calcom_booking_uid=result.booking_uid,
            calcom_booking_id=result.booking_id,
            calcom_event_type_id=self.agent.calcom_event_type_id,
            sync_status="synced",
            last_synced_at=datetime.now(UTC),
        )
        self.db.add(appointment)
        await self.db.commit()
        await self.db.refresh(appointment)

        self.log.info("appointment_created", appointment_id=appointment.id)

    # ── Text-only helpers ───────────────────────────────────────────

    async def _get_contact(self) -> Contact | None:
        """Get contact for this conversation."""
        if not self.conversation.contact_id:
            self.log.warning(
                "no_contact_id_on_conversation",
                conversation_phone=self.conversation.contact_phone,
            )
            return None

        result = await self.db.execute(
            select(Contact).where(Contact.id == self.conversation.contact_id)
        )
        contact = result.scalar_one_or_none()

        self.log.info(
            "contact_lookup",
            contact_id=self.conversation.contact_id,
            found=contact is not None,
        )
        return contact

    def _get_timezone(self) -> ZoneInfo:
        """Get ZoneInfo for configured timezone."""
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("America/New_York")

    def _clean_phone_number(self, phone: str | None) -> str | None:
        """Clean phone number to E.164 format for Cal.com."""
        if not phone:
            return None

        # Remove any non-digit chars except leading +
        cleaned = "".join(c for c in phone if c.isdigit())
        if not phone.startswith("+"):
            cleaned = "1" + cleaned if len(cleaned) == 10 else cleaned
        return "+" + cleaned
