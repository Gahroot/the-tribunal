"""Exercise the real executor/flow with deterministic calendar I/O barriers."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.ai.booking_flow import BookingState
from app.services.ai.tool_executor import VoiceToolExecutor
from app.services.calendar.booking import AvailabilityResult, AvailableSlot, BookingResult

SLOT = {"date": "2026-10-01", "time": "14:00", "iso": "2026-10-01T18:00:00Z"}
BOOK = {"date": SLOT["date"], "time": SLOT["time"], "name": "Alice", "email": "a@example.test"}


@pytest.fixture
def executor(monkeypatch):
    monkeypatch.setattr("app.services.ai.base_tool_executor.settings.calcom_api_key", "test")
    executor = VoiceToolExecutor(
        agent=SimpleNamespace(calcom_event_type_id=123, assignment_strategy="single"),
        contact_info={"name": "Old name"},
    )
    service = SimpleNamespace(
        check_availability=AsyncMock(
            return_value=AvailabilityResult(
                success=True,
                slots=[AvailableSlot(**SLOT)],
            )
        ),
        reserve_slot=AsyncMock(
            return_value={
                "reservationUid": "private-hold-id",
                "reservationUntil": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
        release_slot=AsyncMock(),
        book_appointment=AsyncMock(
            return_value=BookingResult(success=True, booking_uid="booking-1")
        ),
        close=AsyncMock(),
    )
    executor._create_booking_service = Mock(return_value=service)
    executor.post_booking_success = AsyncMock()
    return executor, service


async def offer_and_hold(executor):
    result = await executor.execute("check_availability", {"start_date": SLOT["date"]})
    assert result["booking_state"] == "slot-offered"
    return await executor.execute("hold_booking_slot", {"date": SLOT["date"], "time": SLOT["time"]})


@pytest.mark.asyncio
async def test_booking_uses_held_calendar_and_collected_name_once(executor):
    ex, service = executor
    held = await offer_and_hold(ex)
    assert held["booking_state"] == "collecting-name"
    assert "private-hold-id" not in str(held)
    service.reserve_slot.assert_awaited_once_with(SLOT["iso"])
    result = await ex.execute("book_appointment", BOOK)
    assert result["booking_state"] == "confirmed"
    assert result["booking_uid"] == "booking-1"
    service.release_slot.assert_awaited_once_with("private-hold-id")
    assert service.book_appointment.await_args.kwargs["contact_name"] == "Alice"
    assert await ex.execute("book_appointment", BOOK) == result
    service.book_appointment.assert_awaited_once()
    ex._create_booking_service.assert_called_with(123)


@pytest.mark.asyncio
async def test_cancelling_speech_does_not_cancel_hold(executor):
    ex, service = executor
    started, finish = asyncio.Event(), asyncio.Event()
    reservation = service.reserve_slot.return_value

    async def reserve(_iso):
        started.set()
        await finish.wait()
        return reservation

    service.reserve_slot.side_effect = reserve
    await ex.execute("check_availability", {"start_date": SLOT["date"]})
    waiter = asyncio.create_task(
        ex.execute(
            "hold_booking_slot",
            {
                "date": SLOT["date"],
                "time": SLOT["time"],
            },
        )
    )
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert ex.booking_flow.state == BookingState.HOLDING
    status = await ex.execute("booking_recovery", {"action": "off_script"})
    assert status["booking_state"] == "holding"
    await ex.execute("hold_booking_slot", {"date": SLOT["date"], "time": SLOT["time"]})
    service.reserve_slot.assert_awaited_once()
    finish.set()
    await ex.booking_flow._pending
    assert ex.booking_flow.state == BookingState.COLLECTING_NAME
    resumed = await ex.execute("booking_recovery", {"action": "resume"})
    assert resumed["selected_slot"]["time"] == "14:00"


@pytest.mark.asyncio
async def test_interruption_during_booking_preserves_confirmation(executor):
    ex, service = executor
    await offer_and_hold(ex)
    started, finish = asyncio.Event(), asyncio.Event()

    async def book(**_kwargs):
        started.set()
        await finish.wait()
        return BookingResult(success=True, booking_uid="booking-2")

    service.book_appointment.side_effect = book
    waiter = asyncio.create_task(ex.execute("book_appointment", BOOK))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert (await ex.execute("book_appointment", BOOK))["booking_state"] == "confirming"
    finish.set()
    await ex.booking_flow._pending
    result = await ex.execute("booking_recovery", {"action": "resume"})
    assert result["booking_uid"] == "booking-2"
    service.book_appointment.assert_awaited_once()


@pytest.mark.asyncio
async def test_tangent_resume_and_explicit_change(executor):
    ex, service = executor
    await offer_and_hold(ex)
    assert (await ex.execute("booking_recovery", {"action": "off_script"}))[
        "booking_state"
    ] == "recovery"
    assert not (await ex.execute("book_appointment", BOOK))["success"]
    await ex.execute("booking_recovery", {"action": "off_script"})
    assert (await ex.execute("booking_recovery", {"action": "resume"}))[
        "booking_state"
    ] == "collecting-name"
    service.release_slot.assert_not_awaited()
    assert not (await ex.execute("book_appointment", {**BOOK, "time": "15:00"}))["success"]
    assert not (await ex.execute("book_appointment", {**BOOK, "name": " "}))["success"]
    assert not (await ex.execute("check_availability", {"start_date": SLOT["date"]}))["success"]
    await ex.execute("booking_recovery", {"action": "change_slot"})
    service.release_slot.assert_awaited_once()
    assert ex.booking_flow.state == BookingState.IDLE
    assert ex.booking_flow.selected is None
    service.book_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_hold_cannot_book(executor):
    ex, service = executor
    await offer_and_hold(ex)
    ex.booking_flow.reservation["reservationUntil"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    result = await ex.execute("book_appointment", BOOK)
    assert result["booking_state"] == "idle"
    assert not result["success"]
    service.book_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_booking_failure_is_not_retried(executor):
    ex, service = executor
    await offer_and_hold(ex)
    service.book_appointment.return_value = BookingResult(success=False, error="timeout")
    result = await ex.execute("book_appointment", BOOK)
    assert result["booking_state"] == "uncertain"
    for action in ("resume", "cancel", "change_slot"):
        assert not (await ex.execute("booking_recovery", {"action": action}))["success"]
    await ex.execute("book_appointment", BOOK)
    service.book_appointment.assert_awaited_once()


@pytest.mark.asyncio
async def test_unoffered_and_model_supplied_reservations_are_rejected(executor):
    ex, service = executor
    assert not (await ex.execute("book_appointment", BOOK))["success"]
    assert not (
        await ex.execute(
            "hold_booking_slot",
            {
                "date": SLOT["date"],
                "time": SLOT["time"],
            },
        )
    )["success"]
    await ex.execute("check_availability", {"start_date": SLOT["date"]})
    assert not (
        await ex.execute(
            "hold_booking_slot",
            {
                "date": SLOT["date"],
                "time": SLOT["time"],
                "reservationUid": "other-call",
            },
        )
    )["success"]
    service.reserve_slot.assert_not_awaited()
    service.book_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_calls_do_not_share_holds(executor):
    ex, _service = executor
    await offer_and_hold(ex)
    other = VoiceToolExecutor(agent=ex.agent)
    assert other.booking_flow.state == BookingState.IDLE
    assert other.booking_flow.reservation is None


@pytest.mark.asyncio
async def test_reservation_exception_is_contained(executor):
    ex, service = executor
    service.reserve_slot.side_effect = TimeoutError()
    result = await offer_and_hold(ex)
    assert not result["success"]
    assert result["booking_state"] == "uncertain"
    service.close.assert_awaited()


def test_voice_calendar_disables_network_retries(monkeypatch):
    monkeypatch.setattr("app.services.ai.tool_executor.settings.calcom_api_key", "test")
    ex = VoiceToolExecutor(agent=SimpleNamespace(calcom_event_type_id=123))
    assert ex._create_booking_service()._calcom.max_attempts == 1
