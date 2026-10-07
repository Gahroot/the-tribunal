"""Provider-first appointment cancellation (RF-020).

The CRM must not report a cancellation while the Cal.com booking stays live:
the Cal.com booking is cancelled first, failures leave the CRM untouched,
repeat cancels are no-ops, and CRM-only cancels are explicit.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.appointment import Appointment, AppointmentStatus
from app.schemas.appointment import AppointmentUpdate
from app.services.appointments import appointment_service as svc_module
from app.services.appointments.appointment_service import AppointmentService
from app.services.calendar import calcom as calcom_module
from app.services.calendar import calcom_credentials
from app.services.calendar.calcom import (
    CalComBookingAlreadyCancelledError,
    CalComError,
    CalComNotFoundError,
)
from app.services.calendar.calcom_credentials import CalComCredentialError, CalComCredentials

pytestmark = pytest.mark.asyncio


def _appointment(*, booking_uid: str | None = "sandbox-booking-1", **overrides) -> Appointment:
    now = datetime.now(UTC)
    appt = Appointment(
        id=7,
        workspace_id=uuid.uuid4(),
        contact_id=42,
        agent_id=None,
        scheduled_at=now + timedelta(days=2),
        duration_minutes=30,
        status=AppointmentStatus.SCHEDULED,
        notes="Bring floor plans",
        calcom_booking_uid=booking_uid,
        calcom_booking_id=None,
        calcom_event_type_id=123 if booking_uid else None,
        sync_status="synced" if booking_uid else "pending",
        reminders_sent=[],
        created_at=now,
        updated_at=now,
    )
    appt.contact = None
    for key, value in overrides.items():
        setattr(appt, key, value)
    return appt


def _db(appt: Appointment) -> MagicMock:
    result = MagicMock(scalar_one_or_none=MagicMock(return_value=appt))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def calcom(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    service = MagicMock(cancel_booking=AsyncMock(return_value=True), close=AsyncMock())
    monkeypatch.setattr(calcom_module, "CalComService", MagicMock(return_value=service))
    monkeypatch.setattr(
        calcom_credentials,
        "resolve_calcom_credentials",
        AsyncMock(return_value=CalComCredentials(api_key="test-key", source="workspace")),
    )
    tags = MagicMock(add_tag_to_contact=AsyncMock())
    monkeypatch.setattr(svc_module, "TagService", MagicMock(return_value=tags))
    return service


async def test_provider_backed_cancel_cancels_calcom_first(calcom: MagicMock) -> None:
    appt = _appointment()
    db = _db(appt)

    result = await AppointmentService(db).cancel_appointment(
        appt.workspace_id, appt.id, reason="  Client moved  "
    )

    calcom.cancel_booking.assert_awaited_once_with("sandbox-booking-1", reason="Client moved")
    calcom.close.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert appt.status == AppointmentStatus.CANCELLED
    assert appt.cancellation_reason == "Client moved"
    assert appt.notes == "Bring floor plans"  # reason no longer clobbers notes
    assert appt.sync_status == "synced"
    assert (result.outcome, result.provider_result, result.attendee_notice) == (
        "cancelled",
        "cancelled",
        "provider",
    )


@pytest.mark.parametrize(
    "error",
    [CalComError("API error: upstream 503"), CalComError("Request timeout after 3 attempts")],
)
async def test_provider_failure_leaves_appointment_scheduled(
    calcom: MagicMock, error: Exception
) -> None:
    calcom.cancel_booking.side_effect = error
    appt = _appointment()
    db = _db(appt)

    with pytest.raises(HTTPException) as exc_info:
        await AppointmentService(db).cancel_appointment(appt.workspace_id, appt.id, reason="x")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == "calendar_cancel_failed"
    assert exc_info.value.detail["details"]["retryable"] is True
    assert exc_info.value.detail["details"]["crm_only_available"] is True
    assert appt.status == AppointmentStatus.SCHEDULED
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited()
    calcom.close.assert_awaited_once()


async def test_missing_credentials_fails_without_local_change(
    calcom: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        calcom_credentials,
        "resolve_calcom_credentials",
        AsyncMock(side_effect=CalComCredentialError("calcom_not_configured", "Not set up.")),
    )
    appt = _appointment()
    db = _db(appt)

    with pytest.raises(HTTPException) as exc_info:
        await AppointmentService(db).cancel_appointment(appt.workspace_id, appt.id)

    assert exc_info.value.detail["details"]["retryable"] is False
    assert appt.status == AppointmentStatus.SCHEDULED
    calcom.cancel_booking.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "provider_result"),
    [
        (CalComBookingAlreadyCancelledError("already"), "already_cancelled"),
        (CalComNotFoundError("missing"), "not_found"),
    ],
)
async def test_already_cancelled_or_missing_booking_completes_honestly(
    calcom: MagicMock, error: Exception, provider_result: str
) -> None:
    calcom.cancel_booking.side_effect = error
    appt = _appointment()

    result = await AppointmentService(_db(appt)).cancel_appointment(appt.workspace_id, appt.id)

    assert appt.status == AppointmentStatus.CANCELLED
    assert result.provider_result == provider_result
    assert result.attendee_notice == "none"


async def test_local_only_appointment_skips_provider(calcom: MagicMock) -> None:
    appt = _appointment(booking_uid=None)

    result = await AppointmentService(_db(appt)).cancel_appointment(appt.workspace_id, appt.id)

    calcom.cancel_booking.assert_not_awaited()
    assert appt.status == AppointmentStatus.CANCELLED
    assert appt.sync_status == "pending"
    assert (result.provider, result.provider_result, result.attendee_notice) == (
        "none",
        "not_applicable",
        "none",
    )


async def test_crm_only_cancel_leaves_booking_and_can_be_retried(calcom: MagicMock) -> None:
    appt = _appointment()
    db = _db(appt)
    service = AppointmentService(db)

    first = await service.cancel_appointment(appt.workspace_id, appt.id, crm_only=True)
    assert first.provider_result == "skipped"
    assert appt.sync_status == "local_only"
    calcom.cancel_booking.assert_not_awaited()

    retried = await service.cancel_appointment(appt.workspace_id, appt.id)
    calcom.cancel_booking.assert_awaited_once()
    assert retried.provider_result == "cancelled"
    assert appt.sync_status == "synced"


async def test_repeat_cancel_is_noop_without_provider_call(calcom: MagicMock) -> None:
    appt = _appointment(status=AppointmentStatus.CANCELLED, cancellation_reason="Original")
    db = _db(appt)

    result = await AppointmentService(db).cancel_appointment(
        appt.workspace_id, appt.id, reason="Second click"
    )

    calcom.cancel_booking.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert result.outcome == "already_cancelled"
    assert appt.cancellation_reason == "Original"


async def test_cancel_response_serializes_contact_without_phone(calcom: MagicMock) -> None:
    """A committed cancel must not turn into a 500 for an email-only contact."""
    from app.models.contact import Contact

    appt = _appointment(booking_uid=None)
    appt.contact = Contact(id=42, first_name="Email", last_name=None, email=None, phone_number=None)

    result = await AppointmentService(_db(appt)).cancel_appointment(appt.workspace_id, appt.id)

    assert result.appointment.contact is not None
    assert result.appointment.contact.phone_number is None


async def test_completed_appointment_cannot_be_cancelled(calcom: MagicMock) -> None:
    appt = _appointment(status=AppointmentStatus.COMPLETED)

    with pytest.raises(HTTPException) as exc_info:
        await AppointmentService(_db(appt)).cancel_appointment(appt.workspace_id, appt.id)

    assert exc_info.value.status_code == 409
    calcom.cancel_booking.assert_not_awaited()


async def test_generic_update_to_cancelled_routes_through_provider(calcom: MagicMock) -> None:
    appt = _appointment()

    await AppointmentService(_db(appt)).update_appointment(
        appt.workspace_id, appt.id, AppointmentUpdate(status="cancelled")
    )

    calcom.cancel_booking.assert_awaited_once()
    assert appt.status == AppointmentStatus.CANCELLED
