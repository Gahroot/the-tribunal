"""End-to-end-ish test that the booking tool routes through staff assignment.

Exercises ``VoiceToolExecutor.execute("book_appointment", ...)`` for a
round-robin agent and asserts the booking is created against the *selected
staff member's* Cal.com event type (not the agent's default), and that the
assigned staff is surfaced in the tool result.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import app.db.session as db_session_module
from app.services.ai import base_tool_executor
from app.services.ai.tool_executor import VoiceToolExecutor


class _FakeStaff:
    def __init__(self, name: str, event_type_id: int, count: int = 0) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.calcom_event_type_id = event_type_id
        self.skills: list[str] = []
        self.is_active = True
        self.priority = 0
        self.assignment_count = count
        self.last_assigned_at: datetime | None = None


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, pool: list[Any]) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def execute(self, _query: Any) -> _FakeResult:
        return _FakeResult(self._pool)

    async def scalar(self, query: Any) -> Any:
        params = query.compile().params
        assert "agent_id_1" in params
        return next(
            (
                s
                for s in self._pool
                if s.id == params["id_1"]
                and s.calcom_event_type_id == params["calcom_event_type_id_1"]
                and s.is_active
            ),
            None,
        )

    def add(self, _obj: Any) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, _obj: Any) -> None:
        pass

    async def flush(self) -> None:
        pass


class _FakeBookingService:
    """Captures the event_type_id it was constructed with."""

    captured_event_type_id: int | None = None

    def __init__(
        self, *, api_key: str, event_type_id: int, timezone: str, max_attempts: int = 1
    ) -> None:
        _FakeBookingService.captured_event_type_id = event_type_id

    async def check_availability(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            slots=[
                SimpleNamespace(
                    date="2099-01-15",
                    time="14:00",
                    iso="2099-01-15T19:00:00Z",
                )
            ],
        )

    async def reserve_slot(self, _iso: str) -> dict[str, str]:
        return {
            "reservationUid": "hold-bob",
            "reservationUntil": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }

    async def release_slot(self, uid: str) -> None:
        assert uid == "hold-bob"

    async def book_appointment(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            booking_uid="uid-routed-1",
            booking_id=999,
            error=None,
            alternative_slots=[],
        )

    async def close(self) -> None:
        pass


def _round_robin_agent() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        assignment_strategy="round_robin",
        calcom_event_type_id=1,  # agent default that should NOT be used
    )


@pytest.mark.asyncio
async def test_book_appointment_routes_to_selected_staff_event_type() -> None:
    _FakeBookingService.captured_event_type_id = None
    # Bob has fewer assignments -> round-robin should pick Bob (event type 555).
    pool = [
        _FakeStaff("Alice", event_type_id=444, count=3),
        _FakeStaff("Bob", event_type_id=555, count=0),
    ]

    executor = VoiceToolExecutor(agent=_round_robin_agent())

    with (
        patch.object(base_tool_executor.settings, "calcom_api_key", "test-key"),
        patch.object(db_session_module, "AsyncSessionLocal", return_value=_FakeSession(pool)),
        patch("app.services.calendar.booking.BookingService", _FakeBookingService),
    ):
        offered = await executor.execute("check_availability", {"start_date": "2099-01-15"})
        assert offered["booking_state"] == "slot-offered"
        held = await executor.execute(
            "hold_booking_slot",
            {
                "date": "2099-01-15",
                "time": "14:00",
            },
        )
        assert held["booking_state"] == "collecting-name"
        # Another caller advances round-robin; this call must stay on Bob's calendar.
        pool[1].assignment_count = 10
        result = await executor.execute(
            "book_appointment",
            {
                "date": "2099-01-15",
                "time": "14:00",
                "email": "caller@example.com",
                "name": "Caller",
            },
        )

    assert result["success"] is True
    # Booked against Bob's event type, not the agent's default (1) or Alice's (444).
    assert _FakeBookingService.captured_event_type_id == 555
    assert executor.assigned_staff is not None
    assert executor.assigned_staff["name"] == "Bob"
    assert executor.assigned_staff["calcom_event_type_id"] == 555
    assert "Bob" in result["message"]
    assert pool[1].assignment_count == 11
    assert pool[0].assignment_count == 3
