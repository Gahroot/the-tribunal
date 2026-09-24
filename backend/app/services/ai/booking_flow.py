"""Call-local booking dialog. Speech cancellation must not cancel calendar mutations.

Reservations expire upstream after five minutes even if the call/process disappears.
A failed booking is deliberately not retried: the provider may have accepted it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.services.ai.tool_definitions import TOOL_DEFINITIONS

if TYPE_CHECKING:
    from app.services.ai.tool_executor import VoiceToolExecutor


class BookingState(StrEnum):
    IDLE = "idle"
    SLOT_OFFERED = "slot-offered"
    HOLDING = "holding"
    COLLECTING_NAME = "collecting-name"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    RECOVERY = "recovery"
    UNCERTAIN = "uncertain"


class VoiceBookingFlow:
    """One flow per executor/call; never trust model-supplied reservation IDs."""

    TOOLS = frozenset(
        {
            "check_availability",
            "hold_booking_slot",
            "booking_recovery",
            "book_appointment",
        }
    )

    def __init__(self, executor: VoiceToolExecutor) -> None:
        self.executor = executor
        self.state = BookingState.IDLE
        self.slots: list[dict[str, Any]] = []
        self.selected: dict[str, Any] | None = None
        self.reservation: dict[str, Any] | None = None
        self.event_type_id: int | None = None
        self.skill: str | None = None
        self.name: str | None = None
        self.confirmation: dict[str, Any] | None = None
        self._resume_state = BookingState.IDLE
        self._pending: asyncio.Task[dict[str, Any]] | None = None

    def status(self, *, success: bool = True, message: str | None = None) -> dict[str, Any]:
        prompts = {
            BookingState.IDLE: "Ask which day, then check availability.",
            BookingState.SLOT_OFFERED: "Offer returned slots; hold only the caller's chosen slot.",
            BookingState.HOLDING: "The calendar hold is in progress. Do not start another hold.",
            BookingState.COLLECTING_NAME: "Collect name and email, then book the held slot.",
            BookingState.CONFIRMING: "Booking in progress. Do not retry or claim confirmation.",
            BookingState.CONFIRMED: "The appointment is confirmed. Do not book again.",
            BookingState.RECOVERY: "Answer the question, then resume the saved booking step.",
            BookingState.UNCERTAIN: "Outcome uncertain. Ask a human to verify; do not retry.",
        }
        if self.state == BookingState.CONFIRMED and self.confirmation:
            message = message or self.confirmation.get("message")
        return {
            "success": success,
            "booking_state": self.state.value,
            "message": message or prompts[self.state],
            "selected_slot": self.selected,
            "hold_expires_at": (self.reservation or {}).get("reservationUntil"),
        }

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            args = TOOL_DEFINITIONS[tool].arguments.model_validate(arguments).model_dump()
        except ValidationError:
            return self.status(
                success=False, message="Invalid booking input; check required fields."
            )
        # Inspect/resume is safe during an operation; never cancel or replace its task.
        if self._pending and not self._pending.done():
            return self.status(message="Calendar operation still in progress. Resume shortly.")
        self._pending = asyncio.create_task(self._run(tool, args))
        return await asyncio.shield(self._pending)

    async def _run(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._dispatch(tool, args)
        except Exception:
            # No exception escapes an orphaned shielded task. Fail closed on ambiguous writes.
            self.executor.log.exception("voice_booking_flow_failed", state=self.state.value)
            self.state = BookingState.UNCERTAIN
            return self.status(success=False)

    def _guard(self) -> dict[str, Any] | None:
        if self.state == BookingState.CONFIRMED:
            return {**(self.confirmation or {}), **self.status()}
        if self.state == BookingState.UNCERTAIN:
            return self.status(success=False)
        if self.reservation and self._expired():
            self.reservation = None
            self.selected = None
            self.slots = []
            self.state = BookingState.IDLE
            return self.status(success=False, message="The hold expired. Check availability again.")
        return None

    async def _dispatch(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        guarded = self._guard()
        if guarded is not None:
            return guarded
        if tool == "booking_recovery":
            return await self._recover(args["action"])
        if self.state == BookingState.RECOVERY:
            return self.status(
                success=False, message="Resume the saved step before changing the booking."
            )
        if tool == "check_availability":
            return await self._offer(args)
        if tool == "hold_booking_slot":
            return await self._hold(args)
        return await self._book(args)

    async def _offer(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.reservation:
            return self.status(
                success=False, message="A slot is held. Explicitly change_slot first."
            )
        result = await self.executor._execute_without_booking_flow("check_availability", args)
        self.slots = result.get("slots", []) if result.get("success") else []
        self.skill = args.get("skill")
        self.state = BookingState.SLOT_OFFERED if self.slots else BookingState.IDLE
        return {**result, "booking_state": self.state.value}

    def _expired(self) -> bool:
        assert self.reservation is not None
        until = datetime.fromisoformat(str(self.reservation["reservationUntil"]))
        return until <= datetime.now(UTC)

    async def _hold(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.reservation:
            return self.status(
                success=False, message="Resume the held slot or explicitly change_slot."
            )
        slot = next(
            (
                s
                for s in self.slots
                if s["date"] == args["date"] and s["time"] == args["time"] and s.get("iso")
            ),
            None,
        )
        if not slot or not self.event_type_id:
            return self.status(
                success=False, message="Choose a returned slot after checking availability."
            )
        self.selected = slot.copy()
        self.state = BookingState.HOLDING
        service = self.executor._create_booking_service(self.event_type_id)
        try:
            self.reservation = await service.reserve_slot(slot["iso"])
            # Validate expiry before claiming we have a usable hold.
            if self._expired():
                self.state = BookingState.IDLE
                self.reservation = None
                self.slots = []
                self.selected = None
                return self.status(success=False, message="Hold expired. Check availability again.")
            self.state = BookingState.COLLECTING_NAME
            return self.status()
        finally:
            await service.close()

    async def _release(self) -> None:
        if not self.reservation:
            return
        service = self.executor._create_booking_service(self.event_type_id)
        try:
            await service.release_slot(self.reservation["reservationUid"])
            self.reservation = None
        finally:
            await service.close()

    async def _recover(self, action: str) -> dict[str, Any]:
        if action == "off_script":
            if self.state != BookingState.RECOVERY:
                self._resume_state = self.state
                self.state = BookingState.RECOVERY
        elif action == "resume":
            if self.state == BookingState.RECOVERY:
                self.state = self._resume_state
        elif action in {"cancel", "change_slot"}:
            await self._release()
            self.selected = None
            self.slots = []
            self.name = None
            self.event_type_id = None
            self.state = BookingState.IDLE
        return self.status()

    async def _book(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.state != BookingState.COLLECTING_NAME or not self.selected:
            return self.status(
                success=False, message="Hold the caller's chosen slot before booking."
            )
        if (args["date"], args["time"]) != (self.selected["date"], self.selected["time"]):
            return self.status(
                success=False, message="Do not replace the held slot. Explicitly change_slot first."
            )
        if args.get("skill") not in (None, self.skill):
            return self.status(
                success=False, message="Changing specialists requires a new availability check."
            )
        name = (args.get("name") or "").strip()
        if not name or not (args.get("email") or "").strip():
            return self.status(
                success=False, message="Ask for the caller's name and email before booking."
            )
        self.name = name
        self.state = BookingState.CONFIRMING
        # Cal.com v2 bookings has no reservationUid input. Release our hold immediately
        # before normal conflict-checked booking; never bypass availability conflicts.
        await self._release()
        result = await self.executor._execute_without_booking_flow("book_appointment", args)
        if result.get("success") and result.get("booking_uid"):
            self.confirmation = result
            self.state = BookingState.CONFIRMED
        else:
            self.state = BookingState.UNCERTAIN
        return {**result, **self.status(success=self.state == BookingState.CONFIRMED)}
