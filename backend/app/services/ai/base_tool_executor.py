"""Base tool executor with shared Cal.com booking logic.

Extracts duplicated booking workflow from VoiceToolExecutor and
TextToolExecutor into a single base class. Subclasses inject
channel-specific behavior via hook method overrides.

Usage:
    class MyExecutor(BaseToolExecutor):
        def format_availability_slots(self, slots, start_date):
            ...  # channel-specific formatting
"""

import uuid
from typing import Any

import structlog

from app.core.config import settings  # noqa: F401 - re-exported for test patching
from app.services.calendar.booking import BookingService
from app.services.calendar.calcom_credentials import (
    CALCOM_EVENT_TYPE_MISSING,
    CalComCredentialError,
    CalComCredentials,
    resolve_calcom_credentials,
)

logger = structlog.get_logger()


class BaseToolExecutor:
    """Base class for tool executors with shared Cal.com booking logic.

    Provides the core booking workflow (config validation, service
    instantiation, availability checks, appointment booking) while
    delegating channel-specific formatting and persistence to hook
    methods that subclasses override.
    """

    max_slots: int = 15
    pre_validate: bool = False

    def __init__(self, agent: Any, timezone: str = "America/New_York") -> None:
        self.agent = agent
        self.timezone = timezone
        self.log = logger.bind(service="base_tool_executor")
        # Staff member chosen by round-robin / skill-based routing for the most
        # recent booking attempt (None when the single-event-type path is used).
        self.assigned_staff: dict[str, Any] | None = None
        # Cal.com credentials resolved for this executor's workspace. Never logged.
        self._calcom_credentials: CalComCredentials | None = None

    # ── Config validation ───────────────────────────────────────────

    def _assignment_strategy(self) -> str:
        """Return the agent's booking assignment strategy (defaults to single)."""
        return getattr(self.agent, "assignment_strategy", "single") or "single"

    def _calcom_workspace_id(self) -> uuid.UUID | None:
        """Workspace whose Cal.com connection this executor books against."""
        workspace_id = getattr(self.agent, "workspace_id", None)
        return workspace_id if isinstance(workspace_id, uuid.UUID) else None

    async def _load_calcom_credentials(self) -> CalComCredentials:
        """Resolve workspace Cal.com credentials. Override to reuse a session."""
        workspace_id = self._calcom_workspace_id()
        if workspace_id is None:
            # No workspace context (legacy/test agents): only the documented
            # global fallback can apply, so skip opening a DB session.
            return await resolve_calcom_credentials(None, None)

        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            return await resolve_calcom_credentials(db, workspace_id)

    async def _ensure_calcom_credentials(self) -> dict[str, Any] | None:
        """Resolve (once) and cache Cal.com credentials. Returns an error dict on failure."""
        if self._calcom_credentials is not None:
            return None
        try:
            self._calcom_credentials = await self._load_calcom_credentials()
        except CalComCredentialError as exc:
            self.log.warning("calcom_credentials_unavailable", error_code=exc.code)
            return exc.to_result()
        return None

    async def _validate_calcom_config(self) -> dict[str, Any] | None:
        """Check Cal.com configuration. Returns error dict or None if valid.

        Credentials come from the active workspace's Cal.com integration (with
        the documented global fallback only when the workspace never connected
        Cal.com). With a multi-staff strategy the agent need not have its own
        ``calcom_event_type_id`` — the event type is resolved from the assigned
        staff member at booking time; a missing event type surfaces after staff
        resolution.
        """
        error = await self._ensure_calcom_credentials()
        if error:
            return error
        if self._assignment_strategy() == "single" and (
            not self.agent or not self.agent.calcom_event_type_id
        ):
            return {
                "success": False,
                "error": (
                    "No Cal.com event type is configured for this agent. "
                    "Set the agent's Cal.com event type in agent settings."
                ),
                "error_code": CALCOM_EVENT_TYPE_MISSING,
            }
        return None

    def _calcom_api_key(self) -> str:
        """Return the resolved Cal.com API key (call ``_validate_calcom_config`` first)."""
        if self._calcom_credentials is None:
            raise RuntimeError("Cal.com credentials not resolved for this executor")
        return self._calcom_credentials.api_key

    @staticmethod
    def _no_calendar_error() -> dict[str, Any]:
        return {
            "success": False,
            "error": (
                "No bookable calendar available: neither the assigned staff member nor "
                "the agent has a Cal.com event type."
            ),
            "error_code": CALCOM_EVENT_TYPE_MISSING,
        }

    async def _resolve_event_type_id(
        self, required_skill: str | None, *, record: bool = True
    ) -> int | None:
        """Resolve which Cal.com event type to book against for this attempt.

        Applies the agent's assignment strategy: for round-robin / skill-based
        agents it picks a staff member from the pool and uses their event type,
        recording the choice in ``self.assigned_staff``. Falls back to the
        agent's own ``calcom_event_type_id`` when no staff is selected.

        ``record`` controls whether the selection consumes a round-robin turn.
        Bookings record (default); availability checks pass ``record=False`` so
        they only peek the staff member's event type without skewing
        distribution.
        """
        self.assigned_staff = None
        strategy = self._assignment_strategy()
        default_event_type_id = getattr(self.agent, "calcom_event_type_id", None)
        if strategy == "single":
            return default_event_type_id

        from app.db.session import AsyncSessionLocal
        from app.services.calendar.staff_assignment import (
            resolve_staff_for_booking,
            staff_to_assignment_dict,
        )

        try:
            async with AsyncSessionLocal() as db:
                staff = await resolve_staff_for_booking(
                    db,
                    agent=self.agent,
                    required_skill=required_skill,
                    commit=True,
                    record=record,
                )
                if staff and staff.calcom_event_type_id:
                    self.assigned_staff = staff_to_assignment_dict(staff)
                    return staff.calcom_event_type_id
        except Exception as e:  # pragma: no cover - defensive; fall back to default
            self.log.warning("staff_assignment_failed", error=str(e))

        return default_event_type_id

    def _create_booking_service(self, event_type_id: int | None = None) -> BookingService:
        """Create a BookingService for the resolved (or agent default) event type."""
        return BookingService(
            api_key=self._calcom_api_key(),
            event_type_id=event_type_id or self.agent.calcom_event_type_id,
            timezone=self.timezone,
        )

    # ── Shared tool implementations ─────────────────────────────────

    async def execute_check_availability(
        self,
        start_date_str: str,
        end_date_str: str | None,
        required_skill: str | None = None,
    ) -> dict[str, Any]:
        """Check Cal.com availability. Delegates formatting to hooks."""
        error = await self._validate_calcom_config()
        if error:
            return error

        # Peek only: an availability check must not consume a round-robin turn.
        event_type_id = await self._resolve_event_type_id(required_skill, record=False)
        if not event_type_id:
            return self._no_calendar_error()

        booking_service = self._create_booking_service(event_type_id)
        try:
            result = await booking_service.check_availability(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                max_slots=self.max_slots,
            )

            if not result.success:
                failure: dict[str, Any] = {
                    "success": False,
                    "error": result.error or "Unknown error",
                }
                if result.error_code:
                    failure["error_code"] = result.error_code
                return failure

            if not result.slots:
                return {
                    "success": True,
                    "available": False,
                    "message": f"No available slots on {start_date_str}",
                }

            return self.format_availability_result(result.slots, start_date_str, end_date_str)

        finally:
            await booking_service.close()

    async def execute_book_appointment(
        self,
        date_str: str,
        time_str: str,
        email: str | None,
        duration_minutes: int = 30,
        notes: str | None = None,
        required_skill: str | None = None,
    ) -> dict[str, Any]:
        """Book a Cal.com appointment. Delegates formatting/persistence to hooks."""
        error = await self._validate_calcom_config()
        if error:
            return error

        if not email:
            return {
                "success": False,
                "error": "Email address is required for booking",
                "message": "Please ask the customer for their email address",
            }

        event_type_id = await self._resolve_event_type_id(required_skill)
        if not event_type_id:
            return self._no_calendar_error()

        contact_name = self.get_contact_name()
        contact_phone = self.get_contact_phone()
        metadata = self.get_booking_metadata(notes)

        booking_service = self._create_booking_service(event_type_id)
        try:
            result = await booking_service.book_appointment(
                date_str=date_str,
                time_str=time_str,
                email=email,
                contact_name=contact_name,
                duration_minutes=duration_minutes,
                metadata=metadata,
                phone_number=contact_phone,
                pre_validate=self.pre_validate,
            )

            if not result.success:
                return self.format_booking_failure(result, time_str)

            await self.post_booking_success(
                result,
                date_str,
                time_str,
                email,
                duration_minutes,
                notes,
            )

            return self.format_booking_success(
                result,
                contact_name,
                date_str,
                time_str,
                email,
                duration_minutes,
            )

        finally:
            await booking_service.close()

    # ── Hook methods (override in subclasses) ───────────────────────

    def get_contact_name(self) -> str:
        """Return customer name for booking. Override in subclass."""
        return "Customer"

    def get_contact_phone(self) -> str | None:
        """Return customer phone for booking. Override in subclass."""
        return None

    def get_booking_metadata(self, notes: str | None) -> dict[str, Any] | None:
        """Return metadata dict for the booking. Override in subclass."""
        return {"notes": notes} if notes else None

    def format_availability_result(
        self,
        slots: list[Any],
        start_date_str: str,
        end_date_str: str | None,
    ) -> dict[str, Any]:
        """Format availability slots for channel. Override in subclass."""
        return {
            "success": True,
            "available": True,
            "slots": [{"date": s.date, "time": s.time, "iso": s.iso} for s in slots],
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
        """Format successful booking response. Override in subclass."""
        return {
            "success": True,
            "booking_uid": result.booking_uid,
        }

    def format_booking_failure(
        self,
        result: Any,
        time_str: str,
    ) -> dict[str, Any]:
        """Format failed booking response. Override in subclass."""
        failure: dict[str, Any] = {"success": False, "error": result.error or "Booking failed"}
        if getattr(result, "error_code", None):
            failure["error_code"] = result.error_code
        return failure

    async def post_booking_success(
        self,
        result: Any,
        date_str: str,
        time_str: str,
        email: str,
        duration_minutes: int,
        notes: str | None,
    ) -> None:
        """Post-processing after successful booking. Override in subclass."""

    async def post_booking_attempt(self, success: bool) -> None:
        """Called after any booking attempt (success or failure). Override in subclass."""
