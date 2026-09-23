"""Appointment confirmation and logistics behavior."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.webhooks.calcom_events import DEFAULT_CONFIRMATION_BODY, build_logistics_body
from app.models.conversation import MessageStatus
from app.services.calendar.confirmation_reply import handle_confirmation_reply
from app.workers.reminder_worker import ReminderWorker


def test_confirmation_invites_explicit_reply() -> None:
    assert "Reply C to confirm / R to reschedule" in DEFAULT_CONFIRMATION_BODY


def test_logistics_requires_real_operator_details() -> None:
    assert build_logistics_body(None) is None
    assert build_logistics_body(SimpleNamespace(settings={})) is None
    assert build_logistics_body(
        SimpleNamespace(
            settings={
                "appointment_address": "10 Main St",
                "appointment_parking": "Rear lot",
                "appointment_link": "https://example.com/meet",
            }
        )
    ) == (
        "Appointment details: Address: 10 Main St. Parking: Rear lot. "
        "Meeting link: https://example.com/meet. Reply with questions."
    )


def test_morning_uses_workspace_timezone() -> None:
    worker = ReminderWorker()
    appt = SimpleNamespace(
        workspace=SimpleNamespace(settings={"timezone": "America/New_York"}),
        scheduled_at=datetime(2026, 9, 23, 17, tzinfo=UTC),
    )
    assert not worker._morning_due(appt, datetime(2026, 9, 23, 12, tzinfo=UTC))
    assert worker._morning_due(appt, datetime(2026, 9, 23, 13, tzinfo=UTC))
    assert not worker._morning_due(appt, datetime(2026, 9, 22, 18, tzinfo=UTC))
    appt.scheduled_at = datetime(2026, 9, 23, 12, tzinfo=UTC)  # 8am local
    assert worker._morning_due(appt, datetime(2026, 9, 23, 11, tzinfo=UTC))


@pytest.mark.asyncio
async def test_c_reply_confirms_only_matching_scheduled_appointment() -> None:
    now = datetime.now(UTC)
    appt = SimpleNamespace(
        id=1,
        contact_id=17,
        workspace_id="ws",
        agent_id=None,
        created_at=now - timedelta(days=1),
        scheduled_at=now + timedelta(days=1),
        confirmed_at=None,
        reschedule_requested_at=None,
        reminders_sent=[],
    )
    conversation = SimpleNamespace(
        id=5, contact_id=17, workspace_id="ws", workspace_phone="+15551234567"
    )
    message = SimpleNamespace(created_at=now, conversation_id=5)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [appt]
    db = AsyncMock()
    db.scalar.return_value = now - timedelta(minutes=10)
    db.get.return_value = None
    db.execute.return_value = result
    with patch(
        "app.services.calendar.confirmation_reply.resolve_from_number",
        new_callable=AsyncMock,
        return_value="+15551234567",
    ):
        assert await handle_confirmation_reply(db, message, conversation, " c ")
    assert appt.confirmed_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reply_without_invitation_is_not_consumed() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    now = datetime.now(UTC)
    conversation = SimpleNamespace(
        id=5, contact_id=17, workspace_id="ws", workspace_phone="+15551234567"
    )
    appt = SimpleNamespace(
        contact_id=17,
        workspace_id="ws",
        agent_id=None,
        created_at=now - timedelta(days=1),
        scheduled_at=now + timedelta(days=1),
        id=2,
        reminders_sent=[],
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [appt]
    db.execute.return_value = result
    message = SimpleNamespace(created_at=now)
    with patch(
        "app.services.calendar.confirmation_reply.resolve_from_number",
        new_callable=AsyncMock,
        return_value="+15551234567",
    ):
        assert not await handle_confirmation_reply(db, message, conversation, "R")
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_reconfirm_attempt_is_logged_and_not_redialed() -> None:
    worker = ReminderWorker()
    worker.opt_out_manager.check_opt_out = AsyncMock(return_value=False)
    worker._mark_offset_sent = AsyncMock()
    now = datetime.now(UTC)
    appt = SimpleNamespace(
        id=42,
        workspace_id="ws",
        workspace=SimpleNamespace(settings={"timezone": "UTC"}),
        scheduled_at=now + timedelta(minutes=80),
        contact=SimpleNamespace(phone_number="+15551234567"),
        agent=SimpleNamespace(id="agent", is_active=True),
    )
    db = AsyncMock()
    db.scalar.return_value = "+15557654321"
    voice = MagicMock()
    voice.initiate_call = AsyncMock(return_value=SimpleNamespace(status=MessageStatus.FAILED))
    voice.close = AsyncMock()
    with (
        patch("app.workers.reminder_worker.datetime") as clock,
        patch("app.workers.reminder_worker.settings.telnyx_api_key", "test-key"),
        patch("app.workers.reminder_worker.settings.telnyx_connection_id", "test-conn"),
        patch("app.services.telephony.telnyx_voice.TelnyxVoiceService", return_value=voice),
    ):
        clock.now.return_value = datetime(2026, 9, 23, 14, tzinfo=UTC)
        await worker._send_reconfirm_call(appt, db)
    kwargs = voice.initiate_call.await_args.kwargs
    assert kwargs["call_purpose"] == "appointment_reconfirm:42"
    assert kwargs["idempotency_key"] is not None
    worker._mark_offset_sent.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reply_targets_most_recent_invitation_not_first_appointment() -> None:
    now = datetime.now(UTC)

    def appointment(number: int) -> SimpleNamespace:
        return SimpleNamespace(
            id=number,
            workspace_id="ws",
            contact_id=17,
            agent_id=None,
            created_at=now - timedelta(days=2),
            scheduled_at=now + timedelta(days=number),
            reminders_sent=[],
            confirmed_at=None,
            reschedule_requested_at=None,
        )

    earlier, later = appointment(1), appointment(2)
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [earlier, later]
    db.execute.return_value = result
    db.scalar.side_effect = [now - timedelta(hours=2), now - timedelta(minutes=2)]
    db.get.return_value = None
    conversation = SimpleNamespace(
        id=5, contact_id=17, workspace_id="ws", workspace_phone="+15551234567"
    )
    with patch(
        "app.services.calendar.confirmation_reply.resolve_from_number",
        new_callable=AsyncMock,
        return_value="+15551234567",
    ):
        assert await handle_confirmation_reply(
            db, SimpleNamespace(created_at=now), conversation, "C"
        )
    assert earlier.confirmed_at is None
    assert later.confirmed_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("sent", [True, False])
async def test_reschedule_reply_acknowledges_without_duplicate_booking(sent: bool) -> None:
    now = datetime.now(UTC)
    appt = SimpleNamespace(
        id=9,
        workspace_id="ws",
        contact_id=17,
        agent_id=3,
        created_at=now - timedelta(days=1),
        scheduled_at=now + timedelta(days=1),
        reminders_sent=[],
        confirmed_at=None,
        reschedule_requested_at=None,
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [appt]
    db.execute.return_value = result
    db.scalar.return_value = now - timedelta(minutes=1)
    db.get.side_effect = [
        SimpleNamespace(id=3),
        SimpleNamespace(
            phone_number="+15551234567", email="a@example.com", first_name="A", last_name="B"
        ),
    ]
    conversation = SimpleNamespace(
        id=5, contact_id=17, workspace_id="ws", workspace_phone="+15551234567"
    )
    with (
        patch(
            "app.services.calendar.confirmation_reply.resolve_from_number",
            new_callable=AsyncMock,
            return_value="+15551234567",
        ),
        patch(
            "app.api.webhooks.calcom_events.send_lifecycle_sms",
            new_callable=AsyncMock,
            return_value=sent,
        ) as sender,
    ):
        assert (
            await handle_confirmation_reply(db, SimpleNamespace(created_at=now), conversation, "R")
            is sent
        )
    assert appt.reschedule_requested_at is not None
    assert appt.scheduled_at == now + timedelta(days=1)
    assert "Our team will follow up" in sender.await_args.kwargs["body_text"]
    assert "http" not in sender.await_args.kwargs["body_text"]
    sender.assert_awaited_once()
