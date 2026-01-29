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

from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services.calendar.calcom import CalComService

logger = structlog.get_logger()


class TextToolExecutor:
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
        """Initialize text tool executor.

        Args:
            agent: Agent model with calcom_event_type_id
            conversation: Conversation for contact lookup
            db: Async database session for persistence
            timezone: Timezone for bookings (from workspace)
        """
        self.agent = agent
        self.conversation = conversation
        self.db = db
        self.timezone = timezone
        self.log = logger.bind(
            service="text_tool_executor",
            agent_id=str(agent.id),
            conversation_id=str(conversation.id),
        )

    async def handle_tool_calls(
        self,
        tool_calls: list[ChatCompletionMessageToolCall],
    ) -> list[dict[str, Any]]:
        """Handle tool calls from OpenAI and return results.

        Args:
            tool_calls: List of tool calls from OpenAI response

        Returns:
            List of tool results to send back to OpenAI
        """
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

    async def execute(
        self,
        function_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call.

        Args:
            function_name: Name of function to execute
            arguments: Function arguments from AI

        Returns:
            Tool execution result dictionary
        """
        if function_name == "book_appointment":
            return await self._execute_book_appointment(
                date_str=arguments.get("date", ""),
                time_str=arguments.get("time", ""),
                email=arguments.get("email"),
                duration_minutes=arguments.get("duration_minutes", 30),
                notes=arguments.get("notes"),
            )
        elif function_name == "check_availability":
            return await self._execute_check_availability(
                start_date_str=arguments.get("start_date", ""),
                end_date_str=arguments.get("end_date"),
            )
        else:
            self.log.warning("unknown_text_tool", function_name=function_name)
            return {"success": False, "error": f"Unknown function: {function_name}"}

    async def _execute_book_appointment(  # noqa: PLR0911
        self,
        date_str: str,
        time_str: str,
        email: str | None = None,
        duration_minutes: int = 30,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Execute the book_appointment tool call.

        Creates a booking on Cal.com and saves the appointment to the database.

        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format (24-hour)
            email: Customer email address for booking confirmation
            duration_minutes: Duration in minutes
            notes: Optional notes

        Returns:
            Dict with success status and booking details or error message
        """
        # Check if Cal.com is configured
        if not self.agent.calcom_event_type_id:
            self.log.warning("calcom_not_configured")
            return {
                "success": False,
                "error": "Cal.com event type not configured for this agent",
            }

        if not settings.calcom_api_key:
            self.log.error("calcom_api_key_missing")
            return {
                "success": False,
                "error": "Cal.com API key not configured",
            }

        # Get contact info
        contact = await self._get_contact()
        if not contact:
            return {
                "success": False,
                "error": "Contact not found for this conversation",
            }

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

        # Parse date and time
        try:
            tz = self._get_timezone()
            appointment_datetime = datetime.strptime(
                f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=tz)
        except ValueError as e:
            self.log.warning("invalid_datetime", error=str(e))
            return {
                "success": False,
                "error": f"Invalid date/time format: {e}",
            }

        # Create Cal.com booking
        calcom_service = CalComService(settings.calcom_api_key)
        try:
            # Convert to UTC for Cal.com API
            appointment_utc = appointment_datetime.astimezone(UTC)

            # Clean phone number - Cal.com wants E.164 format
            phone = self._clean_phone_number(contact.phone_number)

            booking_result = await calcom_service.create_booking(
                event_type_id=self.agent.calcom_event_type_id,
                contact_email=booking_email,
                contact_name=contact.full_name or "Customer",
                start_time=appointment_utc,
                duration_minutes=duration_minutes,
                metadata={
                    "source": "ai_text_agent",
                    "agent_id": str(self.agent.id),
                    "conversation_id": str(self.conversation.id),
                },
                timezone=self.timezone,
                language="en",
                phone_number=phone,
            )

            self.log.info(
                "calcom_booking_created",
                booking_uid=booking_result.get("uid"),
                booking_id=booking_result.get("id"),
            )

            # Create appointment record in database
            appointment = Appointment(
                workspace_id=self.conversation.workspace_id,
                contact_id=contact.id,
                agent_id=self.agent.id,
                scheduled_at=appointment_datetime,
                duration_minutes=duration_minutes,
                status="scheduled",
                service_type="video_call",
                notes=notes,
                calcom_booking_uid=booking_result.get("uid"),
                calcom_booking_id=booking_result.get("id"),
                calcom_event_type_id=self.agent.calcom_event_type_id,
                sync_status="synced",
                last_synced_at=datetime.now(UTC),
            )
            self.db.add(appointment)
            await self.db.commit()
            await self.db.refresh(appointment)

            self.log.info("appointment_created", appointment_id=appointment.id)

            formatted_time = appointment_datetime.strftime("%A, %B %d at %I:%M %p")
            return {
                "success": True,
                "booking_uid": booking_result.get("uid"),
                "scheduled_at": appointment_datetime.isoformat(),
                "duration_minutes": duration_minutes,
                "message": f"Appointment booked for {formatted_time}",
            }

        except Exception as e:
            self.log.exception("booking_failed", error=str(e))
            return {
                "success": False,
                "error": f"Failed to create booking: {str(e)}",
            }
        finally:
            await calcom_service.close()

    async def _execute_check_availability(
        self,
        start_date_str: str,
        end_date_str: str | None = None,
    ) -> dict[str, Any]:
        """Execute the check_availability tool call.

        Fetches available time slots from Cal.com.

        Args:
            start_date_str: Start date in YYYY-MM-DD format
            end_date_str: End date in YYYY-MM-DD format (defaults to start_date)

        Returns:
            Dict with available slots or error message
        """
        if not self.agent.calcom_event_type_id:
            return {
                "success": False,
                "error": "Cal.com event type not configured",
            }

        if not settings.calcom_api_key:
            return {
                "success": False,
                "error": "Cal.com API key not configured",
            }

        try:
            tz = self._get_timezone()
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=tz
            )
            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=tz
                )
            else:
                end_date = start_date.replace(hour=23, minute=59, second=59)

        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid date format: {e}",
            }

        calcom_service = CalComService(settings.calcom_api_key)
        try:
            slots = await calcom_service.get_availability(
                event_type_id=self.agent.calcom_event_type_id,
                start_date=start_date,
                end_date=end_date,
                timezone=self.timezone,
            )

            self.log.info("availability_checked", slot_count=len(slots))

            # Format slots for AI consumption with date and time
            formatted_slots = []
            for slot in slots[:15]:  # Limit to 15 slots
                slot_date = slot.get("date", "")
                slot_time = slot.get("time", slot.get("start", ""))
                if slot_date and slot_time:
                    # Format as "Monday Jan 6 at 2:00 PM" for better AI understanding
                    try:
                        slot_dt = datetime.strptime(
                            f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M"
                        )
                        formatted = slot_dt.strftime("%A %b %d at %I:%M %p")
                        formatted_slots.append(formatted)
                    except ValueError:
                        # Fallback to raw format
                        formatted_slots.append(f"{slot_date} {slot_time}")
                elif slot_time:
                    formatted_slots.append(slot_time)

            if not formatted_slots and slots:
                # Fallback: return raw slot data if formatting failed
                self.log.warning("slot_formatting_fallback", raw_slots=slots[:5])
                formatted_slots = [str(s) for s in slots[:10]]

            return {
                "success": True,
                "available_slots": formatted_slots,
                "slot_count": len(slots),
                "date_range": f"{start_date_str} to {end_date_str or start_date_str}",
            }

        except Exception as e:
            self.log.exception("availability_check_failed", error=str(e))
            return {
                "success": False,
                "error": f"Failed to check availability: {str(e)}",
            }
        finally:
            await calcom_service.close()

    async def _get_contact(self) -> Contact | None:
        """Get contact for this conversation.

        Returns:
            Contact model or None if not found
        """
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
        """Get ZoneInfo for configured timezone.

        Returns:
            ZoneInfo object, defaulting to America/New_York
        """
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("America/New_York")

    def _clean_phone_number(self, phone: str | None) -> str | None:
        """Clean phone number to E.164 format for Cal.com.

        Args:
            phone: Raw phone number

        Returns:
            E.164 formatted phone number or None
        """
        if not phone:
            return None

        # Remove any non-digit chars except leading +
        cleaned = "".join(c for c in phone if c.isdigit())
        if not phone.startswith("+"):
            cleaned = "1" + cleaned if len(cleaned) == 10 else cleaned
        return "+" + cleaned
