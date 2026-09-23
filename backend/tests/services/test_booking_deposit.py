"""Deposit assignment and signed-checkout reconciliation contracts."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.appointments import refund_deposit
from app.models.appointment import Appointment
from app.services.appointments.appointment_service import AppointmentService
from app.services.payments import booking_deposit


def appointment() -> Appointment:
    return Appointment(
        id=17,
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        contact_id=42,
    )


def test_assignment_stays_in_original_arm() -> None:
    appt = appointment()
    booking_deposit.assign_deposit(appt, "experiment")
    assigned = (appt.deposit_experiment, appt.deposit_amount_cents, appt.deposit_status)
    assert assigned[0] is True
    assert assigned[1] in (0, 2000, 5000)
    booking_deposit.assign_deposit(appt, "50")
    assert (appt.deposit_experiment, appt.deposit_amount_cents, appt.deposit_status) == assigned


@pytest.mark.asyncio
async def test_recovered_checkout_link_uses_session_scoped_sms_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.webhooks import calcom_events

    appt = appointment()
    appt.deposit_status = "pending"
    appt.deposit_amount_cents = 2000
    appt.deposit_checkout_url = "https://checkout.stripe.com/test"
    appt.deposit_checkout_session_id = "cs_123"
    appt.created_at = datetime.now(UTC) - timedelta(days=2)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(calcom_events, "send_lifecycle_sms", send)
    db = MagicMock()
    contact = SimpleNamespace(id=appt.contact_id, phone_number="+15551234567")

    assert not await booking_deposit.deliver_deposit_link(db, appt, contact, None)
    assert await booking_deposit.deliver_deposit_link(db, appt, contact, None, newly_created=True)
    assert appt.deposit_checkout_url in send.await_args.args[4]
    assert send.await_args.kwargs == {
        "idempotency_scope": "booking_deposit_checkout_link",
        "idempotency_parts": (appt.id, "cs_123"),
    }


def test_reminder_never_sends_expired_checkout_link() -> None:
    appt = appointment()
    appt.deposit_status = "pending"
    appt.deposit_amount_cents = 2000
    appt.deposit_checkout_url = "https://checkout.stripe.com/test"
    appt.created_at = datetime.now(UTC) - timedelta(days=2)
    assert booking_deposit.deposit_message(appt) == ""
    appt.created_at = datetime.now(UTC)
    assert appt.deposit_checkout_url in booking_deposit.deposit_message(appt)


@pytest.mark.asyncio
async def test_sync_retry_offers_and_delivers_missing_checkout_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    appt = appointment()
    appt.workspace_id = workspace_id
    appt.deposit_status = "pending"
    appt.sync_status = "pending"
    appt.calcom_event_type_id = 14
    contact = SimpleNamespace(
        id=appt.contact_id,
        first_name="Guest",
        last_name="Example",
        email="guest@example.com",
        phone_number="+15551234567",
    )
    agent = SimpleNamespace(id=appt.agent_id)
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: contact),
            SimpleNamespace(scalar_one_or_none=lambda: agent),
            SimpleNamespace(scalar_one_or_none=lambda: contact),
            SimpleNamespace(scalar_one_or_none=lambda: agent),
        ]
    )
    service = AppointmentService(db)
    service.get_appointment = AsyncMock(return_value=appt)

    async def sync_success(**kwargs: object) -> None:
        appt.sync_status = "synced"
        appt.calcom_booking_uid = "booking_123"

    service._try_calcom_sync = AsyncMock(side_effect=sync_success)

    async def create_checkout(*args: object) -> None:
        appt.deposit_checkout_session_id = "cs_recovered"

    appt.created_at = datetime.now(UTC) - timedelta(days=2)
    offer = AsyncMock(side_effect=create_checkout)
    deliver = AsyncMock()
    monkeypatch.setattr(booking_deposit, "offer_deposit_checkout", offer)
    monkeypatch.setattr(booking_deposit, "deliver_deposit_link", deliver)

    result = await service.sync_to_calcom(workspace_id, appt.id)
    assert result == {"status": "synced", "calcom_booking_uid": "booking_123"}
    offer.assert_awaited_once_with(db, appt, contact.email)
    deliver.assert_awaited_once_with(db, appt, contact, agent, newly_created=True)

    # A subsequent retry can recover Checkout without making a second booking.
    await service.sync_to_calcom(workspace_id, appt.id)
    service._try_calcom_sync.assert_awaited_once()
    assert offer.await_count == 2
    assert deliver.await_args.kwargs == {"newly_created": False}


@pytest.mark.asyncio
async def test_checkout_requires_matching_paid_session_and_refundable_intent() -> None:
    appt = appointment()
    appt.deposit_amount_cents = 2000
    appt.deposit_status = "pending"
    appt.deposit_checkout_session_id = "cs_expected"
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: appt))
    db.commit = AsyncMock()
    event = {
        "id": "cs_expected",
        "status": "complete",
        "mode": "payment",
        "payment_status": "paid",
        "currency": "usd",
        "amount_total": 2000,
        "metadata": {"appointment_id": "17"},
    }
    for changes in (
        {"payment_intent": None},
        {"payment_intent": "pi_1", "amount_total": 5000},
        {"payment_intent": "pi_1", "id": "cs_other"},
    ):
        await booking_deposit.reconcile_checkout(event | changes, db)
        assert appt.deposit_status == "pending"
    assert db.commit.await_count == 0
    await booking_deposit.reconcile_checkout(event | {"payment_intent": "pi_1"}, db)
    assert appt.deposit_status == "paid"
    assert appt.deposit_payment_intent_id == "pi_1"
    await booking_deposit.reconcile_checkout(event | {"payment_intent": "pi_1"}, db)
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_refund_denies_non_admin_and_other_workspace() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    workspace_id = uuid.uuid4()
    user = SimpleNamespace(id=1)
    with pytest.raises(HTTPException) as denied:
        await refund_deposit(workspace_id, 17, user, db, SimpleNamespace(id=workspace_id))
    assert denied.value.status_code == 403
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(role="admin")),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]
    )
    with pytest.raises(HTTPException) as missing:
        await refund_deposit(workspace_id, 17, user, db, SimpleNamespace(id=workspace_id))
    assert missing.value.status_code == 404
    assert "appointments.workspace_id" in str(db.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_refund_records_stripe_id_and_reuses_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stripe

    appt = SimpleNamespace(
        id=17, deposit_status="paid", deposit_payment_intent_id="pi_1", deposit_refund_id=None
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(role="admin")),
            SimpleNamespace(scalar_one_or_none=lambda: appt),
        ]
    )
    db.commit = AsyncMock()
    refund_create = MagicMock(return_value=SimpleNamespace(id="re_1", status="pending"))
    monkeypatch.setattr(
        stripe,
        "StripeClient",
        lambda _: SimpleNamespace(refunds=SimpleNamespace(create=refund_create)),
    )
    monkeypatch.setattr("app.core.config.settings.stripe_secret_key", "test-only-key")
    workspace_id = uuid.uuid4()
    result = await refund_deposit(
        workspace_id, 17, SimpleNamespace(id=1), db, SimpleNamespace(id=workspace_id)
    )
    assert result == {"status": "refund_pending"}
    assert appt.deposit_refund_id == "re_1"
    assert refund_create.call_args.kwargs["options"]["idempotency_key"].endswith("-first")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_refund_keeps_deposit_paid_and_allows_new_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stripe

    appt = SimpleNamespace(
        id=17, deposit_status="paid", deposit_payment_intent_id="pi_1", deposit_refund_id=None
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(role="owner")),
            SimpleNamespace(scalar_one_or_none=lambda: appt),
        ]
    )
    db.commit = AsyncMock()
    monkeypatch.setattr(
        stripe,
        "StripeClient",
        lambda _: SimpleNamespace(
            refunds=SimpleNamespace(
                create=lambda **_: SimpleNamespace(id="re_failed", status="failed")
            )
        ),
    )
    monkeypatch.setattr("app.core.config.settings.stripe_secret_key", "test-only-key")
    workspace_id = uuid.uuid4()
    with pytest.raises(HTTPException) as failed:
        await refund_deposit(
            workspace_id, 17, SimpleNamespace(id=1), db, SimpleNamespace(id=workspace_id)
        )
    assert failed.value.status_code == 502
    assert appt.deposit_status == "paid"
    assert appt.deposit_refund_id == "re_failed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_card_setup_requires_completed_setup_intent() -> None:
    appt = appointment()
    appt.deposit_amount_cents = 0
    appt.deposit_status = "pending"
    appt.deposit_checkout_session_id = "cs_card"
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: appt))
    db.commit = AsyncMock()
    event = {
        "id": "cs_card",
        "mode": "setup",
        "status": "complete",
        "metadata": {"appointment_id": "17"},
    }
    await booking_deposit.reconcile_checkout(event, db)
    assert appt.deposit_status == "pending"
    await booking_deposit.reconcile_checkout(event | {"setup_intent": "seti_1"}, db)
    assert appt.deposit_status == "pending"
    await booking_deposit.reconcile_checkout(
        event | {"setup_intent": "seti_1", "customer": "cus_1"}, db
    )
    assert appt.deposit_status == "card_saved"
    assert appt.deposit_setup_intent_id == "seti_1"
    assert appt.deposit_stripe_customer_id == "cus_1"
    assert db.commit.await_count == 1
