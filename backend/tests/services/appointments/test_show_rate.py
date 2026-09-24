"""Regression checks for no-show classification and deal stage transitions."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.appointments import show_rate, waitlist
from app.services.opportunities import appointment_stages
from app.workers.noshow_reengagement_worker import (
    _DEFAULT_DAY3_TEMPLATE,
    _DEFAULT_DAY7_TEMPLATE,
    NoshowReengagementWorker,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "confirmed,cause,opposite",
    [
        (True, "confirmed-then-no-show", "never-confirmed"),
        (False, "never-confirmed", "confirmed-then-no-show"),
    ],
)
async def test_noshow_records_per_appointment_cause_and_moves_deal(
    monkeypatch, confirmed, cause, opposite
):
    workspace_id = uuid.uuid4()
    contact = SimpleNamespace(
        id=13, workspace_id=workspace_id, noshow_count=0, last_appointment_status=None
    )
    appointment = SimpleNamespace(
        id=44,
        contact_id=13,
        workspace_id=workspace_id,
        status="no_show",
        confirmed_at=datetime.now(UTC) if confirmed else None,
        scheduled_at=datetime.now(UTC),
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=False)
    db.execute = AsyncMock(
        side_effect=[MagicMock(scalar_one_or_none=MagicMock(return_value=contact)), MagicMock()]
    )
    tags = MagicMock(add_tag_to_contact=AsyncMock())
    monkeypatch.setattr(show_rate, "TagService", lambda db: tags)
    move = AsyncMock()
    monkeypatch.setattr(show_rate, "move_appointment_opportunities", move)

    await show_rate.record_appointment_outcome(db, appointment)

    names = [call.kwargs["name"] for call in tags.add_tag_to_contact.await_args_list]
    assert names == ["no-show", f"noshow-{cause}", f"noshow-{cause}-44"]
    assert opposite not in names
    assert contact.noshow_count == 1
    move.assert_awaited_once_with(db, workspace_id, 13, "no_show")


async def test_newer_booking_preserves_scheduled_lifecycle(monkeypatch):
    workspace_id = uuid.uuid4()
    contact = SimpleNamespace(
        id=13, workspace_id=workspace_id, noshow_count=0, last_appointment_status="scheduled"
    )
    appointment = SimpleNamespace(
        id=44,
        contact_id=13,
        workspace_id=workspace_id,
        status="no_show",
        confirmed_at=None,
        scheduled_at=datetime.now(UTC),
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(scalar_one_or_none=MagicMock(return_value=contact)), MagicMock()]
    )
    db.scalar = AsyncMock(return_value=True)
    tags = MagicMock(add_tag_to_contact=AsyncMock())
    monkeypatch.setattr(show_rate, "TagService", lambda db: tags)
    move = AsyncMock()
    monkeypatch.setattr(show_rate, "move_appointment_opportunities", move)

    await show_rate.record_appointment_outcome(db, appointment)

    assert contact.noshow_count == 1
    assert contact.last_appointment_status == "scheduled"
    move.assert_not_awaited()


async def test_stage_transition_keeps_closed_deals_out_of_query():
    workspace_id, pipeline_id = uuid.uuid4(), uuid.uuid4()
    deal = SimpleNamespace(
        pipeline_id=pipeline_id, stage_id=None, probability=0, stage_changed_at=None
    )
    stage = SimpleNamespace(id=uuid.uuid4(), probability=60)
    db = MagicMock()
    db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[deal])))
    db.scalar = AsyncMock(side_effect=[SimpleNamespace(id=pipeline_id), stage])

    await appointment_stages.move_appointment_opportunities(db, workspace_id, 13, "completed")

    statement = db.scalars.await_args.args[0]
    assert "opportunities.status = :status_1" in str(statement)
    assert "opportunities.workspace_id = :workspace_id_1" in str(statement)
    assert deal.stage_id == stage.id
    assert deal.probability == 60
    assert deal.stage_changed_at is not None


async def test_waitlist_skips_opted_out_contact_and_offers_freed_slot(monkeypatch):
    workspace_id = uuid.uuid4()
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    appt = SimpleNamespace(
        id=44,
        workspace_id=workspace_id,
        contact_id=13,
        agent_id=None,
        calcom_event_type_id=123,
        status="no_show",
        confirmed_at=datetime.now(UTC),
        scheduled_at=start,
        calcom_booking_uid="booking-44",
    )
    blocked = SimpleNamespace(
        id=14, first_name="A", last_name=None, email=None, phone_number="+14155550111"
    )
    eligible = SimpleNamespace(
        id=15, first_name="B", last_name=None, email="b@example.com", phone_number="+14155550222"
    )
    db = MagicMock()
    db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[blocked, eligible])))
    opt_out = MagicMock(check_opt_out=AsyncMock(side_effect=[True, False]))
    monkeypatch.setattr(waitlist, "OptOutManager", lambda: opt_out)
    monkeypatch.setattr(waitlist.settings, "calcom_api_key", "test-key")
    cal = MagicMock(
        generate_booking_url=MagicMock(return_value="https://cal.com/open"),
        cancel_booking=AsyncMock(return_value=True),
        get_availability=AsyncMock(return_value=[{"iso": start.isoformat()}]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(waitlist, "CalComService", lambda key: cal)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(waitlist, "send_lifecycle_sms", send)

    await waitlist.offer_waitlist_opening(db, appt)

    assert send.await_args.kwargs["contact"] is eligible
    assert send.await_args.kwargs["idempotency_parts"] == (44, 15)
    assert start.strftime("%b %d at %I:%M %p UTC") in send.await_args.kwargs["body_text"]
    cal.cancel_booking.assert_awaited_once()
    cal.get_availability.assert_awaited_once()


async def test_future_slot_not_offered_when_calcom_does_not_show_it(monkeypatch):
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    appt = SimpleNamespace(
        id=45,
        workspace_id=uuid.uuid4(),
        contact_id=13,
        agent_id=None,
        confirmed_at=datetime.now(UTC),
        status="no_show",
        calcom_booking_uid="booking-45",
        calcom_event_type_id=123,
        scheduled_at=start,
    )
    contact = SimpleNamespace(
        id=15, phone_number="+14155550222", email="b@example.com", first_name="B", last_name="C"
    )
    db = MagicMock(scalars=AsyncMock(return_value=MagicMock(all=lambda: [contact])))
    monkeypatch.setattr(waitlist.settings, "calcom_api_key", "test-key")
    monkeypatch.setattr(
        waitlist, "OptOutManager", lambda: MagicMock(check_opt_out=AsyncMock(return_value=False))
    )
    cal = MagicMock(
        cancel_booking=AsyncMock(return_value=True),
        get_availability=AsyncMock(return_value=[]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(waitlist, "CalComService", lambda key: cal)
    send = AsyncMock()
    monkeypatch.setattr(waitlist, "send_lifecycle_sms", send)

    await waitlist.offer_waitlist_opening(db, appt)

    send.assert_not_awaited()
    cal.close.assert_awaited_once()


async def test_expired_no_show_offers_verified_future_slot_not_expired_time(monkeypatch):
    now = datetime.now(UTC).replace(microsecond=0)
    next_time = now + timedelta(days=1)
    appt = SimpleNamespace(
        id=46,
        workspace_id=uuid.uuid4(),
        contact_id=13,
        agent_id=None,
        confirmed_at=now,
        status="no_show",
        calcom_booking_uid="old-booking",
        calcom_event_type_id=123,
        scheduled_at=now - timedelta(hours=1),
    )
    contact = SimpleNamespace(
        id=15, phone_number="+14155550222", email="b@example.com", first_name="B", last_name="C"
    )
    db = MagicMock(scalars=AsyncMock(return_value=MagicMock(all=lambda: [contact])))
    monkeypatch.setattr(waitlist.settings, "calcom_api_key", "test-key")
    monkeypatch.setattr(
        waitlist, "OptOutManager", lambda: MagicMock(check_opt_out=AsyncMock(return_value=False))
    )
    cal = MagicMock(
        cancel_booking=AsyncMock(),
        get_availability=AsyncMock(return_value=[{"iso": next_time.isoformat()}]),
        generate_booking_url=MagicMock(return_value="https://cal.com/open"),
        close=AsyncMock(),
    )
    monkeypatch.setattr(waitlist, "CalComService", lambda key: cal)
    send = AsyncMock()
    monkeypatch.setattr(waitlist, "send_lifecycle_sms", send)

    await waitlist.offer_waitlist_opening(db, appt)

    cal.cancel_booking.assert_not_awaited()
    assert next_time.strftime("%b %d at %I:%M %p UTC") in send.await_args.kwargs["body_text"]
    assert (
        appt.scheduled_at.strftime("%b %d at %I:%M %p UTC")
        not in send.await_args.kwargs["body_text"]
    )


@pytest.mark.parametrize(
    "cause,expected",
    [
        ("noshow-confirmed-then-no-show", "even after confirming"),
        ("noshow-never-confirmed", "weren't able to confirm"),
    ],
)
async def test_drip_copy_uses_latest_forensic_cause(cause, expected):
    worker = NoshowReengagementWorker()
    worker._build_reschedule_link = lambda contact, agent: "https://cal.com/book"
    contact = SimpleNamespace(first_name="Sam", last_name="Smith")
    for day, template in ((3, _DEFAULT_DAY3_TEMPLATE), (7, _DEFAULT_DAY7_TEMPLATE)):
        message = worker._render_template(template, contact, MagicMock(), cause=cause, day=day)
        assert "https://cal.com/book" in message
        if day == 3:
            assert expected in message
        else:
            assert "time" in message
    custom = worker._render_template(
        "Hi {first_name}, book here: {booking_link}", contact, MagicMock(), cause=cause, day=3
    )
    assert expected in custom
