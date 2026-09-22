"""Stripe checkout / payment-collection CRM assistant tools.

The autonomous iMessage sales agent closes a Prestyj Batch Video Ads deal by
texting the buyer a secure Stripe Checkout link for the pack they chose. This
mirrors the voice ``collect_payment`` flow but runs over the iMessage thread:

1. Resolve the chosen pack's server-side price (never trust a model-supplied
   amount — the price is derived from ``pack_key``).
2. Reuse :mod:`app.services.payments.call_payment_service` to open a hosted
   Stripe Checkout Session (``payment`` mode, ``PAYMENT_KIND`` metadata) and
   persist a :class:`CallPayment` row so the shared billing webhook can mark it
   paid and notify operators — no duplicated Stripe boundary or reconcile path.
3. Deliver the link over iMessage via the unified outbound delivery service.

Only batch packs close autonomously. Add-ons beyond the batch (running ads,
installing AI agents, consulting) are gated by the workspace autonomy mandate
and escalate to a human instead.
"""

from __future__ import annotations

from typing import Any

import stripe
import structlog

from app.db.scope import get_workspace_owned, select_workspace_owned
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services.ai.crm_assistant._tool_context import CRMToolContext, ToolArguments, ToolHandler
from app.services.autonomy_mandate import BATCH_PACKS
from app.services.idempotency import derive_outbound_key
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    outbound_delivery_service,
)
from app.services.payments import call_payment_service

logger = structlog.get_logger()

# Server-side pack catalog keyed by pack_key. The model only chooses *which*
# pack; the price is authoritative here so the AI can never invent an amount.
_PACKS_BY_KEY: dict[str, dict[str, Any]] = {str(pack["pack_key"]): pack for pack in BATCH_PACKS}


def _pack_choices() -> str:
    return ", ".join(
        f"{pack['pack_key']} ({pack['label']} / ${pack['price_cents'] / 100:.0f})"
        for pack in BATCH_PACKS
    )


class PaymentAssistantTools:
    """Create + text Stripe Checkout links for Prestyj batch packs over iMessage."""

    def __init__(self, context: CRMToolContext) -> None:
        self.context = context
        self.log = logger.bind(service="crm_assistant_payment_tools")

    def handlers(self) -> dict[str, ToolHandler]:
        return {"create_checkout_link": self.create_checkout_link}

    async def _latest_conversation(self, contact_id: int) -> Conversation | None:
        result = await self.context.db.execute(
            select_workspace_owned(
                Conversation,
                self.context.workspace_id,
                Conversation.contact_id == contact_id,
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_checkout_link(  # noqa: PLR0911 - sequential guard clauses
        self, args: ToolArguments
    ) -> dict[str, Any]:
        """Generate a Stripe Checkout link for the chosen pack and text it via iMessage.

        Args:
            pack_key: One of the Prestyj batch pack keys (e.g. ``anchor_500``).
            contact_id: The buyer's contact id within this workspace.
            currency: Optional ISO 4217 currency (defaults to USD).
        """
        pack_key = str(args.get("pack_key") or "").strip()
        pack = _PACKS_BY_KEY.get(pack_key)
        if pack is None:
            return {
                "success": False,
                "error": (
                    f"Unknown pack_key '{pack_key}'. Only batch packs can be closed here: "
                    f"{_pack_choices()}. Anything beyond the batch (running ads, installing "
                    "AI agents, consulting) must be escalated to a human, not closed."
                ),
            }

        contact_id = args.get("contact_id")
        if not isinstance(contact_id, int):
            try:
                contact_id = int(contact_id)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return {"success": False, "error": "A valid contact_id is required."}

        if not call_payment_service.is_payment_configured():
            return {"success": False, "error": "Payments are not configured for this workspace."}

        contact = await get_workspace_owned(
            self.context.db, Contact, contact_id, self.context.workspace_id
        )
        if contact is None:
            return {"success": False, "error": "Contact not found"}
        if not contact.phone_number:
            return {"success": False, "error": "Contact has no phone number to text."}

        conversation = await self._latest_conversation(contact_id)
        if conversation is None or not conversation.workspace_phone:
            return {
                "success": False,
                "error": "No iMessage thread found for this contact to send the link from.",
            }

        amount_value = round(int(pack["price_cents"]) / 100, 2)
        currency_code = (str(args.get("currency") or "usd")).strip().lower()[:3] or "usd"
        product_name = f"Prestyj Batch Video Ads — {pack['label']}"

        from app.models.call_payment import CallPayment, CallPaymentStatus

        payment = CallPayment(
            workspace_id=self.context.workspace_id,
            conversation_id=conversation.id,
            contact_id=contact_id,
            amount=amount_value,
            currency=currency_code,
            description=product_name,
            status=CallPaymentStatus.PENDING,
        )
        self.context.db.add(payment)
        await self.context.db.flush()
        payment_id = payment.id

        metadata = {
            "kind": call_payment_service.PAYMENT_KIND,
            "workspace_id": str(self.context.workspace_id),
            "call_payment_id": str(payment_id),
            "contact_id": str(contact_id),
            "pack_key": pack_key,
            "channel": OutboundDeliveryChannel.IMESSAGE.value,
        }

        try:
            checkout = await call_payment_service.create_payment_checkout_session(
                amount=amount_value,
                currency=currency_code,
                product_name=product_name,
                metadata=metadata,
                customer_email=contact.email,
            )
        except stripe.StripeError as exc:
            payment.status = CallPaymentStatus.FAILED
            await self.context.db.flush()
            self.log.error(
                "checkout_link_stripe_error",
                call_payment_id=str(payment_id),
                pack_key=pack_key,
                error=str(exc),
            )
            return {"success": False, "error": "Could not create the payment link right now."}

        if not checkout.url:
            payment.status = CallPaymentStatus.FAILED
            await self.context.db.flush()
            return {"success": False, "error": "The payment provider did not return a link."}

        payment.stripe_checkout_session_id = checkout.session_id
        payment.stripe_payment_intent_id = checkout.payment_intent_id
        payment.payment_link_url = checkout.url
        await self.context.db.flush()

        body = (
            f"Here's your secure checkout for the Prestyj {pack['label']} pack "
            f"(${amount_value:.0f}):\n\n{checkout.url}\n\n"
            "Payment is processed securely by Stripe."
        )
        result = await outbound_delivery_service.deliver(
            self.context.db,
            OutboundDeliveryRequest(
                workspace_id=self.context.workspace_id,
                channel=OutboundDeliveryChannel.IMESSAGE,
                to=contact.phone_number,
                from_=conversation.workspace_phone,
                body=body,
                contact=contact,
                idempotency_key=derive_outbound_key(
                    "crm_assistant_checkout_link", payment_id, checkout.session_id
                ),
                action_type="crm_assistant.create_checkout_link",
            ),
        )

        if result.message is not None:
            payment.sms_message_id = result.message.id
            await self.context.db.flush()

        if not result.delivered:
            self.log.warning(
                "checkout_link_imessage_failed",
                call_payment_id=str(payment_id),
                reason=result.reason,
            )
            return {
                "success": False,
                "payment_id": str(payment_id),
                "checkout_url": checkout.url,
                "error": (
                    "Created the checkout link but couldn't text it over iMessage "
                    f"({result.reason or 'delivery failed'})."
                ),
            }

        self.log.info(
            "checkout_link_sent",
            call_payment_id=str(payment_id),
            pack_key=pack_key,
            amount=amount_value,
            currency=currency_code,
        )
        return {
            "success": True,
            "payment_id": str(payment_id),
            "pack_key": pack_key,
            "amount": amount_value,
            "currency": currency_code,
            "checkout_url": checkout.url,
            "message": (
                f"Texted the {pack['label']} checkout link (${amount_value:.0f}) to "
                f"{contact.first_name or 'the buyer'} over iMessage. Stripe will confirm "
                "payment via webhook and operators are notified automatically once paid."
            ),
        }
