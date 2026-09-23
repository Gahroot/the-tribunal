"""Deposit assignment and signed-checkout reconciliation contracts."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.appointments import refund_deposit
from app.models.appointment import Appointment
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
