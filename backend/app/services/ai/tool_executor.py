"""Voice agent tool execution service.

This module extracts tool execution logic from voice_bridge.py into a
standalone, testable service. Handles execution of:
- check_availability: Query Cal.com for available slots
- book_appointment: Create appointment on Cal.com
- send_dtmf: Send touch-tone digits for IVR navigation

Usage:
    executor = VoiceToolExecutor(agent, contact_info, timezone)
    result = await executor.execute("check_availability", {"start_date": "2024-01-15"})
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.core.config import settings
from app.services.calendar.calcom import CalComService

logger = structlog.get_logger()


def _format_time_12h(time_24h: str) -> str:
    """Convert 24-hour HH:MM to 12-hour AM/PM (e.g. '14:00' -> '2:00 PM')."""
    try:
        dt = datetime.strptime(time_24h, "%H:%M")
        formatted = dt.strftime("%I:%M %p")
        if formatted.startswith("0"):
            formatted = formatted[1:]
        return formatted
    except ValueError:
        return time_24h


class VoiceToolExecutor:
    """Executes voice agent tool calls.

    Handles Cal.com booking operations, DTMF sending, and other
    tool calls from voice agents.

    Attributes:
        agent: Agent model with Cal.com configuration
        contact_info: Contact information for personalization
        timezone: Timezone for date handling
        call_control_id: Telnyx call control ID for DTMF
        logger: Structured logger
    """

    def __init__(
        self,
        agent: Any,
        contact_info: dict[str, Any] | None = None,
        timezone: str = "America/New_York",
        call_control_id: str | None = None,
    ) -> None:
        """Initialize tool executor.

        Args:
            agent: Agent model with Cal.com event type ID
            contact_info: Contact information (name, phone, email)
            timezone: Timezone for bookings (from workspace)
            call_control_id: Telnyx call control ID for DTMF/booking persistence
        """
        self.agent = agent
        self.contact_info = contact_info
        self.timezone = timezone
        self.call_control_id = call_control_id
        self.logger = logger.bind(service="voice_tool_executor")

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
        self.logger.info(
            "executing_voice_tool",
            function_name=function_name,
            arguments=arguments,
        )

        if function_name == "check_availability":
            return await self._execute_check_availability(
                start_date_str=arguments.get("start_date", ""),
                end_date_str=arguments.get("end_date"),
            )

        elif function_name == "book_appointment":
            result = await self._execute_book_appointment(
                date_str=arguments.get("date", ""),
                time_str=arguments.get("time", ""),
                email=arguments.get("email"),
                duration_minutes=arguments.get("duration_minutes", 30),
                notes=arguments.get("notes"),
            )

            # Persist booking outcome to message record
            if self.call_control_id:
                outcome = "success" if result.get("success") else "failed"
                await self._persist_booking_outcome(outcome)

            return result

        elif function_name == "send_dtmf":
            return await self._execute_send_dtmf(
                digits=arguments.get("digits", ""),
            )

        else:
            self.logger.warning("unknown_voice_tool", function_name=function_name)
            return {"success": False, "error": f"Unknown function: {function_name}"}

    async def _execute_check_availability(
        self,
        start_date_str: str,
        end_date_str: str | None,
    ) -> dict[str, Any]:
        """Execute check_availability tool.

        Args:
            start_date_str: Start date in YYYY-MM-DD format
            end_date_str: Optional end date

        Returns:
            Available slots or error
        """
        if not self.agent or not self.agent.calcom_event_type_id:
            return {"success": False, "error": "Cal.com not configured for this agent"}

        if not settings.calcom_api_key:
            return {"success": False, "error": "Cal.com API key not configured"}

        try:
            # Parse dates
            tz = self._get_timezone()
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=tz)
            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=tz)
            else:
                end_date = start_date

            # Get availability from Cal.com
            calcom_service = CalComService(settings.calcom_api_key)
            try:
                slots = await calcom_service.get_availability(
                    event_type_id=self.agent.calcom_event_type_id,
                    start_date=start_date,
                    end_date=end_date,
                    timezone=self.timezone,
                )

                self.logger.info("availability_fetched", slot_count=len(slots))

                # Format slots for voice response
                if not slots:
                    return {
                        "success": True,
                        "available": False,
                        "message": f"No available slots on {start_date_str}",
                    }

                # Add 12-hour display_time to each slot
                for slot in slots:
                    slot["display_time"] = _format_time_12h(slot.get("time", ""))

                # Build voice-friendly message with 12-hour times
                slot_descriptions = []
                for slot in slots[:5]:  # Limit to 5 for voice
                    slot_descriptions.append(slot["display_time"])

                times_list = ", ".join(slot_descriptions)
                return {
                    "success": True,
                    "available": True,
                    "slots": slots[:10],
                    "message": (
                        f"Available times: {times_list}. "
                        "IMPORTANT: ONLY offer these exact times to the customer. "
                        "Do NOT make up or guess other available times."
                    ),
                }

            finally:
                await calcom_service.close()

        except Exception as e:
            self.logger.exception("check_availability_error", error=str(e))
            return {"success": False, "error": f"Failed to check availability: {e!s}"}

    async def _execute_book_appointment(
        self,
        date_str: str,
        time_str: str,
        email: str | None,
        duration_minutes: int,
        notes: str | None,
    ) -> dict[str, Any]:
        """Execute book_appointment tool.

        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format
            email: Customer email address
            duration_minutes: Appointment duration
            notes: Optional notes

        Returns:
            Booking confirmation or error
        """
        if not self.agent or not self.agent.calcom_event_type_id:
            return {"success": False, "error": "Cal.com not configured for this agent"}

        if not settings.calcom_api_key:
            return {"success": False, "error": "Cal.com API key not configured"}

        if not email:
            return {
                "success": False,
                "error": "Email address is required for booking",
                "message": "Please ask the customer for their email address",
            }

        # Get contact name
        contact_name = "Customer"
        contact_phone = None
        if self.contact_info:
            contact_name = self.contact_info.get("name", "Customer")
            contact_phone = self.contact_info.get("phone")

        calcom_service = CalComService(settings.calcom_api_key)
        try:
            # Pre-validate: check if the requested slot is still available
            tz = self._get_timezone()
            start_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
            slots = await calcom_service.get_availability(
                event_type_id=self.agent.calcom_event_type_id,
                start_date=start_date,
                end_date=start_date,
                timezone=self.timezone,
            )

            # Find the matching slot to get its ISO time
            matched_slot = next(
                (s for s in slots if s.get("time") == time_str),
                None,
            )
            if not matched_slot:
                # Slot is no longer available — return fresh alternatives
                display_time = _format_time_12h(time_str)
                alternative_slots = []
                for s in slots[:5]:
                    alternative_slots.append({
                        "time": s.get("time", ""),
                        "display_time": _format_time_12h(s.get("time", "")),
                    })

                alt_times = ", ".join(s["display_time"] for s in alternative_slots)
                self.logger.warning(
                    "booking_slot_unavailable",
                    requested_time=time_str,
                    available_count=len(slots),
                )
                return {
                    "success": False,
                    "error": (
                        f"The {display_time} slot is no longer available. "
                        "Do NOT re-offer this time to the customer."
                    ),
                    "alternative_slots": alternative_slots,
                    "message": (
                        f"That time is no longer available. "
                        f"{'Available alternatives: ' + alt_times + '. ' if alt_times else ''}"
                        "ONLY offer these exact alternative times. "
                        "Do NOT re-offer the failed time."
                    ),
                }

            # Use the ISO time directly from Cal.com — avoids timezone
            # double-conversion issues (Cal.com returns organizer-local times
            # with misleading Z suffix)
            # Prefer ISO from slot; fall back to constructed string for legacy slots
            start_iso = matched_slot.get("iso", "") or f"{date_str}T{time_str}:00.000Z"

            booking = await calcom_service.create_booking(
                event_type_id=self.agent.calcom_event_type_id,
                contact_email=email,
                contact_name=contact_name,
                start_time_iso=start_iso,
                duration_minutes=duration_minutes,
                metadata={"notes": notes} if notes else None,
                timezone=self.timezone,
                phone_number=contact_phone,
            )

            booking_uid = booking.get("uid")
            booking_id = booking.get("id")

            self.logger.info(
                "booking_created",
                booking_uid=booking_uid,
                booking_id=booking_id,
                email=email,
            )

            display_time = _format_time_12h(time_str)
            return {
                "success": True,
                "booking_id": booking_uid,
                "booking_uid": booking_uid,
                "calcom_id": booking_id,
                "message": (
                    f"Appointment booked for {contact_name} on {date_str} "
                    f"at {display_time}. "
                    f"Confirmation email sent to {email}."
                ),
            }

        except Exception as e:
            self.logger.exception("book_appointment_error", error=str(e))
            return {"success": False, "error": f"Failed to book appointment: {e!s}"}
        finally:
            await calcom_service.close()

    async def _execute_send_dtmf(self, digits: str) -> dict[str, Any]:
        """Execute send_dtmf tool for IVR navigation.

        Args:
            digits: DTMF digits to send

        Returns:
            Success/failure result
        """
        from app.services.telephony.telnyx_voice import TelnyxVoiceService

        # Validate inputs
        error_msg: str | None = None
        if not self.call_control_id:
            self.logger.error("send_dtmf_no_call_control_id")
            error_msg = "No active call to send DTMF"
        elif not digits:
            error_msg = "No digits provided"
        elif not settings.telnyx_api_key:
            error_msg = "Telnyx API key not configured"
        else:
            # Validate digits
            valid_chars = set("0123456789*#ABCDabcdwW")
            invalid = [c for c in digits if c not in valid_chars]
            if invalid:
                error_msg = f"Invalid DTMF characters: {invalid}. Valid: 0-9, *, #, A-D, w, W"
            else:
                # Ensure at least one actual digit is present (not just pause chars)
                actual_digits = set("0123456789*#ABCDabcd")
                has_actual_digit = any(c in actual_digits for c in digits)
                if not has_actual_digit:
                    error_msg = (
                        "DTMF must include at least one digit (0-9, *, #, A-D). "
                        "You sent only pause characters. To navigate an IVR menu, "
                        "send the number for the option you want (e.g., '2' for sales)."
                    )

        if error_msg:
            return {"success": False, "error": error_msg}

        # At this point we know call_control_id is not None
        assert self.call_control_id is not None

        try:
            voice_service = TelnyxVoiceService(settings.telnyx_api_key)
            try:
                success = await voice_service.send_dtmf(
                    call_control_id=self.call_control_id,
                    digits=digits,
                )
            finally:
                await voice_service.close()

            if success:
                self.logger.info(
                    "dtmf_sent_via_tool",
                    call_control_id=self.call_control_id,
                    digits=digits,
                )
                return {
                    "success": True,
                    "message": f"Sent DTMF tones: {digits}",
                    "digits": digits,
                }
            return {"success": False, "error": "Failed to send DTMF tones"}

        except Exception as e:
            self.logger.exception("send_dtmf_error", error=str(e), digits=digits)
            return {"success": False, "error": f"Failed to send DTMF: {e!s}"}

    async def _persist_booking_outcome(self, outcome: str) -> None:
        """Persist booking outcome to message record.

        Args:
            outcome: Booking outcome (e.g., "success", "failed")
        """
        if not self.call_control_id:
            return

        from sqlalchemy import update

        from app.db.session import AsyncSessionLocal
        from app.models.conversation import Message as MessageModel

        async with AsyncSessionLocal() as db:
            try:
                await db.execute(
                    update(MessageModel)
                    .where(MessageModel.provider_message_id == self.call_control_id)
                    .values(booking_outcome=outcome)
                )
                await db.commit()
                self.logger.info(
                    "booking_outcome_persisted",
                    call_control_id=self.call_control_id,
                    outcome=outcome,
                )
            except Exception as e:
                await db.rollback()
                self.logger.error(
                    "booking_outcome_persistence_failed",
                    call_control_id=self.call_control_id,
                    outcome=outcome,
                    error=str(e),
                )

    def _get_timezone(self) -> ZoneInfo:
        """Get ZoneInfo for configured timezone.

        Returns:
            ZoneInfo object, defaulting to America/New_York
        """
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("America/New_York")


def create_tool_callback(
    agent: Any,
    contact_info: dict[str, Any] | None,
    timezone: str,
    call_control_id: str | None,
    log: Any,
) -> Any:
    """Create a tool callback function for voice sessions.

    This is a factory function that creates a callback closure
    capturing all the context needed for tool execution.

    Args:
        agent: Agent model with Cal.com config
        contact_info: Contact information
        timezone: Workspace timezone
        call_control_id: Telnyx call control ID
        log: Logger instance

    Returns:
        Async callback function for voice session tool calls
    """
    executor = VoiceToolExecutor(
        agent=agent,
        contact_info=contact_info,
        timezone=timezone,
        call_control_id=call_control_id,
    )

    async def tool_callback(
        call_id: str,
        function_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        log.info(
            "tool_callback_invoked",
            call_id=call_id,
            function_name=function_name,
            arguments=arguments,
        )
        result = await executor.execute(function_name, arguments)
        log.info(
            "tool_callback_completed",
            call_id=call_id,
            function_name=function_name,
            result=result,
        )
        return result

    return tool_callback
