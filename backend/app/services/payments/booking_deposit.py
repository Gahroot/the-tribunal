"""Optional booking deposit experiment and Stripe Checkout reconciliation.

The assignment is a deterministic contact-level arm, not a payment-completion
cohort: unpaid bookings still count towards their assigned arm's show rate.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment
from app.services.payments.call_payment_service import create_payment_checkout_session

logger = structlog.get_logger()


def assign_deposit(appointment: Appointment, mode: str | None) -> None:
    """Assign once, before committing the booking; never change an existing arm."""
    if appointment.deposit_amount_cents is not None or appointment.deposit_status is not None:
        return
    if mode == "experiment":
        key = f"{appointment.workspace_id}:{appointment.agent_id}:{appointment.contact_id}"
        amount = (0, 2000, 5000)[
            int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % 3
        ]
    elif mode in ("20", "50"):
        amount = int(mode) * 100
    elif mode == "card":
        amount = 0
    else:
        return
    appointment.deposit_experiment = mode == "experiment"
    appointment.deposit_amount_cents = amount
    appointment.deposit_status = "none" if mode == "experiment" and amount == 0 else "pending"


async def offer_deposit_checkout(
    db: AsyncSession, appointment: Appointment, email: str | None
) -> None:
    """Create one optional Checkout link after booking, with a Stripe idempotency key.

    Failures leave the booking in place; another delivery can retry without charging
    twice. The payment result is NEVER inferred from the success redirect.
    """
    if appointment.deposit_status != "pending" or appointment.deposit_checkout_session_id:
        return
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        logger.warning("booking_deposit_stripe_unavailable", appointment_id=appointment.id)
        return
    try:
        result = await create_payment_checkout_session(
            amount=(appointment.deposit_amount_cents or 0) / 100,
            currency="usd",
            product_name="Refundable appointment deposit"
            if appointment.deposit_amount_cents
            else "Optional appointment card on file",
            metadata={"kind": "booking_deposit", "appointment_id": str(appointment.id)},
            customer_email=email,
            idempotency_key=f"booking-deposit-{appointment.id}",
            save_card=appointment.deposit_amount_cents == 0,
            card_only=True,
        )
    except stripe.StripeError:
        logger.exception("booking_deposit_checkout_failed", appointment_id=appointment.id)
        return
    appointment.deposit_checkout_session_id = result.session_id
    appointment.deposit_checkout_url = result.url
    await db.commit()


def deposit_message(appointment: Appointment) -> str:
    """Truthful, optional payment text for booking confirmation and reminders."""
    # Checkout links expire after 24 hours by default. Never send a stale link
    # in a reminder; the booking itself is unaffected.
    created_at = appointment.created_at
    link_is_fresh = not created_at or datetime.now(UTC) - created_at.replace(
        tzinfo=created_at.tzinfo or UTC
    ).astimezone(UTC) < timedelta(hours=23)
    if (
        appointment.deposit_status == "pending"
        and appointment.deposit_checkout_url
        and link_is_fresh
    ):
        if appointment.deposit_amount_cents:
            return (
                f" Optional refundable ${appointment.deposit_amount_cents // 100} deposit: "
                f"{appointment.deposit_checkout_url} Booking is confirmed even if you skip it."
            )
        return f" Optionally save a card (no charge): {appointment.deposit_checkout_url}"
    if appointment.deposit_status == "paid":
        return " Your refundable deposit has been received."
    if appointment.deposit_status == "card_saved":
        return " Your card is on file; no deposit was charged."
    if appointment.deposit_status == "refunded":
        return " Your deposit has been refunded."
    return ""


async def reconcile_checkout(session: dict[str, Any], db: AsyncSession) -> None:
    """Only signed Stripe webhook payloads may mark a deposit paid/card saved."""
    if session.get("status") != "complete" or (
        session.get("mode") == "payment" and session.get("payment_status") != "paid"
    ):
        return
    metadata = session.get("metadata") or {}
    session_id = session.get("id")
    try:
        appointment_id = int(metadata.get("appointment_id", ""))
    except (TypeError, ValueError):
        return
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    appointment = result.scalar_one_or_none()
    if not appointment or not session_id or appointment.deposit_checkout_session_id != session_id:
        return
    if appointment.deposit_status != "pending":
        return
    expected_mode = "payment" if appointment.deposit_amount_cents else "setup"
    if session.get("mode") != expected_mode:
        return
    if (
        expected_mode == "payment"
        and (
            session.get("amount_total") != appointment.deposit_amount_cents
            or session.get("currency") != "usd"
            or not isinstance(session.get("payment_intent"), str)
        )
    ) or (
        expected_mode == "setup"
        and (
            not isinstance(session.get("setup_intent"), str)
            or not isinstance(session.get("customer"), str)
        )
    ):
        return
    appointment.deposit_status = "paid" if expected_mode == "payment" else "card_saved"
    if expected_mode == "payment":
        appointment.deposit_payment_intent_id = session["payment_intent"]
    else:
        appointment.deposit_setup_intent_id = session["setup_intent"]
        appointment.deposit_stripe_customer_id = session["customer"]
    appointment.deposit_checkout_url = None
    await db.commit()
