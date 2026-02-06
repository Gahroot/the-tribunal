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

import structlog

from app.core.config import settings
from app.services.ai.base_tool_executor import BaseToolExecutor

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


class VoiceToolExecutor(BaseToolExecutor):
    """Executes voice agent tool calls.

    Handles Cal.com booking operations, DTMF sending, and other
    tool calls from voice agents.

    Attributes:
        agent: Agent model with Cal.com configuration
        contact_info: Contact information for personalization
        timezone: Timezone for date handling
        call_control_id: Telnyx call control ID for DTMF
        log: Structured logger
    """

    max_slots = 10
    pre_validate = True

    def __init__(
        self,
        agent: Any,
        contact_info: dict[str, Any] | None = None,
        timezone: str = "America/New_York",
        call_control_id: str | None = None,
    ) -> None:
        super().__init__(agent=agent, timezone=timezone)
        self.contact_info = contact_info
        self.call_control_id = call_control_id
        self.log = logger.bind(service="voice_tool_executor")

    # ── Main dispatch ───────────────────────────────────────────────

    async def execute(
        self,
        function_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call."""
        self.log.info(
            "executing_voice_tool",
            function_name=function_name,
            arguments=arguments,
        )

        if function_name == "check_availability":
            return await self.execute_check_availability(
                start_date_str=arguments.get("start_date", ""),
                end_date_str=arguments.get("end_date"),
            )

        if function_name == "book_appointment":
            result = await self.execute_book_appointment(
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

        if function_name == "send_dtmf":
            return await self._execute_send_dtmf(
                digits=arguments.get("digits", ""),
            )

        self.log.warning("unknown_voice_tool", function_name=function_name)
        return {"success": False, "error": f"Unknown function: {function_name}"}

    # ── Hook overrides ──────────────────────────────────────────────

    def get_contact_name(self) -> str:
        if self.contact_info:
            name: str = self.contact_info.get("name", "Customer")
            return name
        return "Customer"

    def get_contact_phone(self) -> str | None:
        if self.contact_info:
            return self.contact_info.get("phone")
        return None

    def format_availability_result(
        self,
        slots: list[Any],
        start_date_str: str,
        end_date_str: str | None,
    ) -> dict[str, Any]:
        """Format slots for voice response with 12-hour display times."""
        slots_dicts = []
        for slot in slots:
            slots_dicts.append({
                "date": slot.date,
                "time": slot.time,
                "iso": slot.iso,
                "display_time": _format_time_12h(slot.time),
            })

        # Build voice-friendly message (limit to 5 for speaking)
        slot_descriptions = [s["display_time"] for s in slots_dicts[:5]]
        times_list = ", ".join(slot_descriptions)

        return {
            "success": True,
            "available": True,
            "slots": slots_dicts,
            "message": (
                f"Available times: {times_list}. "
                "IMPORTANT: ONLY offer these exact times to the customer. "
                "Do NOT make up or guess other available times."
            ),
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
        display_time = _format_time_12h(time_str)
        return {
            "success": True,
            "booking_id": result.booking_uid,
            "booking_uid": result.booking_uid,
            "calcom_id": result.booking_id,
            "message": (
                f"Appointment booked for {contact_name} on {date_str} "
                f"at {display_time}. "
                f"Confirmation email sent to {email}."
            ),
        }

    def format_booking_failure(
        self,
        result: Any,
        time_str: str,
    ) -> dict[str, Any]:
        display_time = _format_time_12h(time_str)

        # Build alternative slots info for voice
        if result.alternative_slots:
            alt_slots = [
                {
                    "time": s.time,
                    "display_time": _format_time_12h(s.time),
                }
                for s in result.alternative_slots
            ]
            alt_times = ", ".join(s["display_time"] for s in alt_slots)
            return {
                "success": False,
                "error": (
                    f"The {display_time} slot is no longer available. "
                    "Do NOT re-offer this time to the customer."
                ),
                "alternative_slots": alt_slots,
                "message": (
                    f"That time is no longer available. "
                    f"{'Available alternatives: ' + alt_times + '. ' if alt_times else ''}"
                    "ONLY offer these exact alternative times. "
                    "Do NOT re-offer the failed time."
                ),
            }

        return {"success": False, "error": result.error or "Booking failed"}

    # ── Voice-only tools ────────────────────────────────────────────

    async def _execute_send_dtmf(self, digits: str) -> dict[str, Any]:
        """Execute send_dtmf tool for IVR navigation."""
        from app.services.telephony.telnyx_voice import TelnyxVoiceService

        # Validate inputs
        error_msg: str | None = None
        if not self.call_control_id:
            self.log.error("send_dtmf_no_call_control_id")
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
                self.log.info(
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
            self.log.exception("send_dtmf_error", error=str(e), digits=digits)
            return {"success": False, "error": f"Failed to send DTMF: {e!s}"}

    async def _persist_booking_outcome(self, outcome: str) -> None:
        """Persist booking outcome to message record."""
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
                self.log.info(
                    "booking_outcome_persisted",
                    call_control_id=self.call_control_id,
                    outcome=outcome,
                )
            except Exception as e:
                await db.rollback()
                self.log.error(
                    "booking_outcome_persistence_failed",
                    call_control_id=self.call_control_id,
                    outcome=outcome,
                    error=str(e),
                )


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
