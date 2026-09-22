#!/usr/bin/env python3
"""Prestyj Batch Video Ads full-pipeline end-to-end smoke (Python orchestrator).

The Tribunal autonomously runs the entire Prestyj Batch Video Ads sales
department over iMessage. This script proves the *whole pipe* carries a single
synthetic prospect from ad-library discovery all the way to a collected
payment, exercising the real code paths at every stage:

    1. discover     ad-library Contact (source='ad_library') in the seeded
                    Prestyj workspace.
    2. first-touch  autopilot outbound iMessage through the real outbound
                    delivery stack (-> MacRelayMessageService -> relay HTTP).
    3. inbound      relay webhook -> /webhooks/mac-relay/messages persists the
                    prospect's reply onto the Conversation (driven by the shell
                    via .ezcoder/eyes/http.sh; asserted by ``verify-inbound``).
    4. ai-reply     the AI sales responder (app.services.ai.text_agent) drafts
                    and sends the anchor/close reply over iMessage.
    5. close        the production close tool
                    (app.services.ai.crm_assistant._payment_tools) opens a
                    Stripe Checkout Session for the chosen pack
                    (app.services.payments.call_payment_service) and texts the
                    link, persisting a CallPayment row.
    6. payment      Stripe ``checkout.session.completed`` reconcile webhook
                    (/api/v1/billing/webhook) marks the CallPayment paid
                    (driven by the shell via http.sh; asserted by
                    ``verify-paid``).

Each subcommand prints a single-line JSON result to stdout (``{"ok": true,
...}``) and exits non-zero on failure so ``prestyj_sales_e2e_smoke.sh`` can gate
on it and emit a PASS/FAIL per stage.

Stubbing strategy (so the smoke is deterministic and self-contained):
  - The outbound relay HTTP boundary is an in-process stub relay (no Mac device
    or live daemon needed) — identical to the existing iMessage channel smoke.
  - The OpenAI completion in the ai-reply stage is replaced with a deterministic
    anchor-close draft, but the *entire* real send pipeline (timing, trace,
    mac_relay transport, Message persistence) runs unchanged.
  - The Stripe Checkout Session *creation* boundary is stubbed to return a
    deterministic session id + URL. The CallPayment persistence, metadata, and
    iMessage delivery all run through real code. The payment-reconcile webhook
    is replayed against the live backend with a genuinely signed payload.

Run from the backend directory so pydantic loads ``backend/.env``:

    cd backend && uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py seed \\
        --artifacts-dir ../.ezcoder/eyes/out/prestyj-sales-e2e
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models.call_payment import CallPayment, CallPaymentStatus
from app.models.contact import Contact
from app.models.conversation import (
    Conversation,
    Message,
    MessageChannel,
    MessageDirection,
)
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    outbound_delivery_service,
)
from app.services.payments import call_payment_service
from app.services.payments.call_payment_service import CheckoutSessionResult
from app.utils.phone import normalize_phone_e164

# Keep stdout machine-parseable: the only thing emitted there is the JSON result
# line. ``DEBUG=true`` in backend/.env turns on SQLAlchemy echo; mute it.
for _noisy in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# The deterministic Prestyj demo workspace seeded by ``scripts.seed_prestyj``.
WORKSPACE_SLUG = "prestyj-batch-video-ads-demo"
# Prestyj iMessage sender identity. The relay (and the conversation
# ``workspace_phone``, VARCHAR(20)) addresses the workspace by this value, and
# the outbound mac_relay transport normalizes it as a phone/email — so we use the
# sender's E.164 number (matching the existing iMessage channel smoke). The seed
# step pins the demo PhoneNumber's ``mac_relay_sender_id`` to this so inbound ->
# conversation -> outbound all resolve to one coherent thread.
SENDER_PHONE = "+18885550197"
SENDER_ADDRESS = SENDER_PHONE

# A dedicated synthetic prospect for the smoke. Deterministic so re-runs are
# clean and it never collides with the 20 seeded ad-library advertisers.
PROSPECT_CONTACT_ID = 9_980_001
PROSPECT_PHONE = "+13105550148"
PROSPECT_EMAIL = "prestyj-smoke-prospect@example.com"
PROSPECT_FIRST = "Dana"
PROSPECT_LAST = "Okafor"
PROSPECT_COMPANY = "Smoke Test Advertiser Co"

# The pack the AI anchors on / closes (matches the seed default_pack_key).
CLOSE_PACK_KEY = "anchor_500"
CLOSE_PACK_AMOUNT = 2500.0
CLOSE_PACK_LABEL = "500 ads"

FIRST_TOUCH_BODY = (
    "Hey Dana - noticed Smoke Test Advertiser has been running the same paid "
    "social creative for a while. We turn one selfie-style recording into "
    "hundreds of vertical ad variations. Worth a look?"
)
INBOUND_BODY = "Yeah I'm interested. What's the cost for the 500 ad pack?"
AI_CLOSE_BODY = (
    "Love it. The 500-ad pack at $2,500 is the sweet spot - enough volume to "
    "properly test hooks, angles, and CTAs. I'll text you a secure Stripe "
    "checkout link now so we can lock your batch in."
)

# Deterministic Stripe identifiers for the stubbed Checkout Session.
STUB_SESSION_ID = "cs_test_prestyj_smoke_0001"
STUB_PAYMENT_INTENT_ID = "pi_test_prestyj_smoke_0001"
STUB_CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_prestyj_smoke_0001"


def _print(result: dict[str, Any]) -> None:
    import sys

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


async def _require_workspace(db: Any) -> Workspace:
    workspace = (
        await db.execute(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
    ).scalar_one_or_none()
    if workspace is None:
        msg = (
            f"Prestyj workspace '{WORKSPACE_SLUG}' is not seeded. Run it first: "
            "cd backend && uv run python -m scripts.seed_prestyj"
        )
        raise RuntimeError(msg)
    return workspace


async def _require_phone(db: Any, workspace_id: uuid.UUID) -> PhoneNumber:
    phone = (
        await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.phone_number == SENDER_PHONE,
            )
        )
    ).scalar_one_or_none()
    if phone is None:
        msg = f"Prestyj iMessage sender '{SENDER_PHONE}' not found; re-run seed_prestyj."
        raise RuntimeError(msg)
    return phone


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


async def _ensure_workspace_seeded() -> None:
    async with AsyncSessionLocal() as db:
        exists = (
            await db.execute(select(Workspace.id).where(Workspace.slug == WORKSPACE_SLUG))
        ).first()
    if exists is None:
        from scripts.seed_prestyj import seed as seed_prestyj

        await seed_prestyj()


async def _reset_prospect_state(db: Any, workspace_id: uuid.UUID) -> None:
    """Remove any prior smoke conversation/messages/payments for a clean run."""
    await db.execute(delete(CallPayment).where(CallPayment.contact_id == PROSPECT_CONTACT_ID))
    convo_ids = (
        await db.execute(
            select(Conversation.id).where(
                Conversation.workspace_id == workspace_id,
                Conversation.contact_id == PROSPECT_CONTACT_ID,
            )
        )
    ).scalars().all()
    if convo_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(convo_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(convo_ids)))
    await db.commit()


async def _upsert_prospect(db: Any, workspace_id: uuid.UUID) -> Contact:
    contact = await db.get(Contact, PROSPECT_CONTACT_ID)
    if contact is None:
        contact = Contact(id=PROSPECT_CONTACT_ID, workspace_id=workspace_id)
        db.add(contact)
    contact.workspace_id = workspace_id
    contact.first_name = PROSPECT_FIRST
    contact.last_name = PROSPECT_LAST
    contact.email = PROSPECT_EMAIL
    contact.phone_number = PROSPECT_PHONE
    contact.company_name = PROSPECT_COMPANY
    contact.status = "new"
    contact.lead_score = 91
    contact.is_qualified = True
    contact.source = "ad_library"
    contact.website_url = "https://smoketestadvertiser.example"
    contact.business_intel = {
        "source": "ad_library",
        "niche": "Home services",
        "location": "Los Angeles, CA",
        "recommended_pack_key": CLOSE_PACK_KEY,
    }
    contact.enrichment_status = "enriched"
    await db.flush()
    # ``email_hash``/``phone_hash`` are filled by the Contact insert listener; on
    # an UPDATE path force them so phone lookups in the inbound pipeline resolve.
    from app.core.encryption import hash_phone, hash_value

    contact.email_hash = hash_value(PROSPECT_EMAIL)
    contact.phone_hash = hash_phone(PROSPECT_PHONE)
    await db.flush()
    return contact


async def seed(artifacts_dir: Path) -> dict[str, Any]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    await _ensure_workspace_seeded()

    inbound_guid = f"prestyj-e2e-{uuid.uuid4()}"
    inbound_provider_message_id = f"mac-relay:{inbound_guid}"
    normalized_prospect = normalize_phone_e164(PROSPECT_PHONE)

    async with AsyncSessionLocal() as db:
        workspace = await _require_workspace(db)
        phone = await _require_phone(db, workspace.id)
        # Pin the relay sender identity to a normalizable address so the inbound
        # webhook, AI reply, and close link all share one coherent thread.
        if phone.mac_relay_sender_id != SENDER_ADDRESS:
            phone.mac_relay_sender_id = SENDER_ADDRESS
            await db.flush()
        await _reset_prospect_state(db, workspace.id)
        contact = await _upsert_prospect(db, workspace.id)
        operator = (
            await db.execute(
                select(WorkspaceMembership.user_id)
                .where(WorkspaceMembership.workspace_id == workspace.id)
                .order_by(WorkspaceMembership.is_default.desc())
                .limit(1)
            )
        ).scalars().first()
        await db.commit()
        workspace_id = str(workspace.id)
        contact_id = contact.id
        contact_source = contact.source
        phone_id = str(phone.id)
        agent_id = str(phone.assigned_agent_id) if phone.assigned_agent_id else None

    # Inbound webhook body (minimal but realistic relay event), addressed to the
    # workspace by its sender identity.
    payload = {
        "event_id": inbound_guid,
        "guid": inbound_guid,
        "from": PROSPECT_PHONE,
        "to": SENDER_ADDRESS,
        "text": INBOUND_BODY,
        "is_from_me": False,
        "service": "imessage",
    }
    (artifacts_dir / "inbound_payload.json").write_text(json.dumps(payload, indent=2) + "\n")

    webhook_token = settings.mac_relay_webhook_token or settings.mac_relay_token
    context = {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "phone_number_id": phone_id,
        "contact_id": contact_id,
        "sender": SENDER_ADDRESS,
        "prospect_phone": PROSPECT_PHONE,
        "normalized_prospect_phone": normalized_prospect,
        "close_pack_key": CLOSE_PACK_KEY,
        "first_touch_body": FIRST_TOUCH_BODY,
        "inbound_body": INBOUND_BODY,
        "ai_close_body": AI_CLOSE_BODY,
        "inbound_guid": inbound_guid,
        "inbound_provider_message_id": inbound_provider_message_id,
        "webhook_token": webhook_token,
        "stripe_webhook_secret_present": bool(settings.stripe_webhook_secret),
        "operator_user_id": operator,
    }
    (artifacts_dir / "context.json").write_text(json.dumps(context, indent=2) + "\n")

    ok = bool(contact_id) and contact_source == "ad_library" and agent_id is not None
    return {
        "ok": ok,
        "step": "seed",
        "workspace_id": workspace_id,
        "contact_id": contact_id,
        "contact_source": contact_source,
        "assigned_agent_id": agent_id,
        "sender": SENDER_ADDRESS,
        "inbound_provider_message_id": inbound_provider_message_id,
        "webhook_token_present": bool(webhook_token),
        "stripe_webhook_secret_present": bool(settings.stripe_webhook_secret),
        "artifacts_dir": str(artifacts_dir),
        "checks": {
            "contact_persisted": bool(contact_id),
            "contact_source_ad_library": contact_source == "ad_library",
            "sender_has_agent": agent_id is not None,
        },
    }


# ---------------------------------------------------------------------------
# Stub relay (in-process) shared by first-touch / ai-reply / close
# ---------------------------------------------------------------------------


class _StubRelayState:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    @property
    def count(self) -> int:
        return len(self.payloads)


def _make_stub_handler(state: _StubRelayState, token: str) -> type[BaseHTTPRequestHandler]:
    class StubRelayHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            return None

        def _json(self, code: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/messages":
                self._json(404, {"error": "not_found"})
                return
            if self.headers.get("Authorization", "") != f"Bearer {token}":
                self._json(401, {"error": "unauthorized"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                payload = {}
            state.payloads.append(payload)
            self._json(
                200,
                {"id": payload.get("client_message_id") or str(uuid.uuid4()), "status": "sent"},
            )

    return StubRelayHandler


class _StubRelay:
    """Context manager that runs the stub relay and points settings at it."""

    def __init__(self) -> None:
        self.state = _StubRelayState()
        self._server: ThreadingHTTPServer | None = None
        self._saved: dict[str, Any] = {}

    def __enter__(self) -> _StubRelayState:
        token = settings.mac_relay_token or "smoke-relay-token"
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _make_stub_handler(self.state, token)
        )
        port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._saved = {
            "base_url": settings.mac_relay_base_url,
            "provider": settings.text_message_provider,
            "token": settings.mac_relay_token,
        }
        settings.mac_relay_base_url = f"http://127.0.0.1:{port}"
        settings.mac_relay_token = token
        settings.text_message_provider = "mac_relay"
        return self.state

    def __exit__(self, *_exc: Any) -> None:
        settings.mac_relay_base_url = self._saved["base_url"]
        settings.text_message_provider = self._saved["provider"]
        settings.mac_relay_token = self._saved["token"]
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


# ---------------------------------------------------------------------------
# first-touch (autopilot outbound)
# ---------------------------------------------------------------------------


async def first_touch() -> dict[str, Any]:
    with _StubRelay() as relay:
        async with AsyncSessionLocal() as db:
            workspace = await _require_workspace(db)
            phone = await _require_phone(db, workspace.id)
            request = OutboundDeliveryRequest(
                workspace_id=workspace.id,
                channel=OutboundDeliveryChannel.IMESSAGE,
                to=PROSPECT_PHONE,
                from_=SENDER_ADDRESS,
                body=FIRST_TOUCH_BODY,
                agent_id=phone.assigned_agent_id,
                phone_number_id=phone.id,
                action_type="prestyj_e2e_first_touch",
            )
            result = await outbound_delivery_service.deliver(db, request)

    relay_payload = relay.payloads[-1] if relay.payloads else {}
    checks = {
        "delivery_sent": result.delivered,
        "relay_received_request": relay.count >= 1,
        "provider_is_mac_relay": (result.provider or "").lower() in {"mac_relay", "imessage"},
        "message_persisted": result.message is not None,
        "channel_is_imessage": result.message is not None
        and result.message.channel == MessageChannel.IMESSAGE,
        "direction_outbound": result.message is not None
        and result.message.direction
        in {MessageDirection.OUTBOUND, MessageDirection.OUTBOUND.value, "outbound"},
        "relay_text_matches": relay_payload.get("text") == FIRST_TOUCH_BODY,
    }
    return {
        "ok": all(checks.values()),
        "step": "first-touch",
        "provider": result.provider,
        "provider_message_id": result.provider_message_id,
        "message_id": str(result.message.id) if result.message else None,
        "reason": result.reason,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# verify-inbound
# ---------------------------------------------------------------------------


async def verify_inbound(context_path: Path) -> dict[str, Any]:
    context = json.loads(context_path.read_text())
    workspace_id = uuid.UUID(context["workspace_id"])
    provider_message_id = context["inbound_provider_message_id"]
    sender = context["sender"]
    expected_contact = context.get("normalized_prospect_phone") or context["prospect_phone"]

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Message, Conversation)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Message.provider_message_id == provider_message_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
        ).first()

    if row is None:
        return {
            "ok": False,
            "step": "verify-inbound",
            "error": "inbound_message_not_found",
            "provider_message_id": provider_message_id,
        }

    message, conversation = row
    checks = {
        "message_persisted": True,
        "direction_inbound": message.direction
        in {MessageDirection.INBOUND, MessageDirection.INBOUND.value, "inbound"},
        "channel_imessage": message.channel == MessageChannel.IMESSAGE,
        "body_matches": message.body == INBOUND_BODY,
        "conversation_sender_matches": conversation.workspace_phone == sender,
        "conversation_contact_matches": conversation.contact_phone == expected_contact,
        "conversation_linked_to_contact": conversation.contact_id == PROSPECT_CONTACT_ID,
        "conversation_ai_enabled": bool(conversation.ai_enabled),
        "conversation_ai_not_paused": not bool(conversation.ai_paused),
        "conversation_has_agent": conversation.assigned_agent_id is not None,
    }
    return {
        "ok": all(checks.values()),
        "step": "verify-inbound",
        "message_id": str(message.id),
        "conversation_id": str(conversation.id),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# ai-reply (real responder, deterministic draft)
# ---------------------------------------------------------------------------


async def ai_reply(context_path: Path) -> dict[str, Any]:
    context = json.loads(context_path.read_text())
    workspace_id = uuid.UUID(context["workspace_id"])

    async with AsyncSessionLocal() as db:
        conversation = (
            await db.execute(
                select(Conversation).where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.contact_id == PROSPECT_CONTACT_ID,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return {"ok": False, "step": "ai-reply", "error": "conversation_not_found"}
        conversation_id = conversation.id
        outbound_before = (
            await db.execute(
                select(Message.id).where(
                    Message.conversation_id == conversation_id,
                    Message.direction == "outbound",
                )
            )
        ).scalars().all()

    # Patch only the OpenAI completion + credential gate; the rest of the
    # responder (timing, mac_relay transport, Message persistence, trace) is the
    # real production path.
    import app.services.ai.text_agent as text_agent

    async def _fake_generate(*_args: Any, **_kwargs: Any) -> str:
        return AI_CLOSE_BODY

    saved_generate = text_agent.generate_text_response
    saved_token = text_agent.get_openai_bearer_token
    text_agent.generate_text_response = _fake_generate  # type: ignore[assignment]
    text_agent.get_openai_bearer_token = lambda: "sk-prestyj-smoke-stub"  # type: ignore[assignment]

    with _StubRelay() as relay:
        try:
            async with AsyncSessionLocal() as db:
                await text_agent.process_inbound_with_ai(
                    conversation_id=conversation_id,
                    workspace_id=workspace_id,
                    db=db,
                    # Pretend the inbound arrived "long ago" so the human-like
                    # send delay collapses to zero for the smoke.
                    response_started_at=time.monotonic() - 3600,
                )
        finally:
            text_agent.generate_text_response = saved_generate  # type: ignore[assignment]
            text_agent.get_openai_bearer_token = saved_token  # type: ignore[assignment]

    async with AsyncSessionLocal() as db:
        ai_message = (
            await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.direction == "outbound",
                    Message.id.notin_(outbound_before) if outbound_before else Message.id.isnot(None),
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    relay_payload = relay.payloads[-1] if relay.payloads else {}
    checks = {
        "relay_received_reply": relay.count >= 1,
        "ai_message_persisted": ai_message is not None,
        "ai_message_outbound": ai_message is not None
        and ai_message.direction
        in {MessageDirection.OUTBOUND, MessageDirection.OUTBOUND.value, "outbound"},
        "ai_message_channel_imessage": ai_message is not None
        and ai_message.channel == MessageChannel.IMESSAGE,
        "ai_message_body_matches": ai_message is not None and ai_message.body == AI_CLOSE_BODY,
        "relay_text_matches": relay_payload.get("text") == AI_CLOSE_BODY,
    }
    return {
        "ok": all(checks.values()),
        "step": "ai-reply",
        "conversation_id": str(conversation_id),
        "ai_message_id": str(ai_message.id) if ai_message else None,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# close (real close tool, stubbed Stripe session creation)
# ---------------------------------------------------------------------------


async def close(artifacts_dir: Path) -> dict[str, Any]:
    from app.services.ai.crm_assistant._payment_tools import PaymentAssistantTools
    from app.services.ai.crm_assistant._tool_context import CRMToolContext

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    async def _fake_session(**_kwargs: Any) -> CheckoutSessionResult:
        return CheckoutSessionResult(
            session_id=STUB_SESSION_ID,
            url=STUB_CHECKOUT_URL,
            payment_intent_id=STUB_PAYMENT_INTENT_ID,
        )

    saved_create = call_payment_service.create_payment_checkout_session
    saved_secret = settings.stripe_secret_key
    call_payment_service.create_payment_checkout_session = _fake_session  # type: ignore[assignment]
    settings.stripe_secret_key = saved_secret or "sk_test_prestyj_smoke"

    try:
        with _StubRelay() as relay:
            async with AsyncSessionLocal() as db:
                workspace = await _require_workspace(db)
                operator = (
                    await db.execute(
                        select(WorkspaceMembership.user_id).where(
                            WorkspaceMembership.workspace_id == workspace.id
                        )
                    )
                ).scalars().first()
                tools = PaymentAssistantTools(
                    CRMToolContext(
                        db=db,
                        workspace_id=workspace.id,
                        user_id=operator or 0,
                    )
                )
                result = await tools.create_checkout_link(
                    {"pack_key": CLOSE_PACK_KEY, "contact_id": PROSPECT_CONTACT_ID}
                )
                await db.commit()
    finally:
        call_payment_service.create_payment_checkout_session = saved_create  # type: ignore[assignment]
        settings.stripe_secret_key = saved_secret

    payment_id = result.get("payment_id")
    async with AsyncSessionLocal() as db:
        payment = await db.get(CallPayment, uuid.UUID(payment_id)) if payment_id else None
        payment_status = payment.status if payment else None
        session_id = payment.stripe_checkout_session_id if payment else None
        link_url = payment.payment_link_url if payment else None
        amount = float(payment.amount) if payment else None

    relay_payload = relay.payloads[-1] if relay.payloads else {}
    checks = {
        "tool_success": bool(result.get("success")),
        "call_payment_created": payment is not None,
        "status_pending": payment_status == CallPaymentStatus.PENDING,
        "session_id_recorded": session_id == STUB_SESSION_ID,
        "checkout_url_recorded": link_url == STUB_CHECKOUT_URL,
        "amount_is_anchor": amount == CLOSE_PACK_AMOUNT,
        # The unified delivery stack rewrites the checkout URL into a tracked
        # short link, so assert a link was texted (not the exact Stripe URL,
        # which is preserved on CallPayment.payment_link_url above).
        "link_texted_over_imessage": relay.count >= 1
        and "http" in str(relay_payload.get("text", "")).lower(),
    }

    if payment is not None:
        stripe_event = {
            "id": f"evt_prestyj_smoke_{uuid.uuid4().hex[:16]}",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": STUB_SESSION_ID,
                    "object": "checkout.session",
                    "mode": "payment",
                    "payment_status": "paid",
                    "status": "complete",
                    "payment_intent": STUB_PAYMENT_INTENT_ID,
                    "metadata": {
                        "kind": call_payment_service.PAYMENT_KIND,
                        "call_payment_id": str(payment_id),
                        "pack_key": CLOSE_PACK_KEY,
                    },
                }
            },
        }
        # Compact, stable bytes so the signature computed later matches exactly.
        (artifacts_dir / "stripe_payload.json").write_text(
            json.dumps(stripe_event, separators=(",", ":"))
        )

    return {
        "ok": all(checks.values()),
        "step": "close",
        "payment_id": payment_id,
        "pack_key": CLOSE_PACK_KEY,
        "amount": amount,
        "session_id": session_id,
        "checkout_url": link_url,
        "checks": checks,
        "tool_error": result.get("error"),
    }


# ---------------------------------------------------------------------------
# stripe-sig (compute a valid Stripe-Signature header for the payload file)
# ---------------------------------------------------------------------------


def stripe_sig(payload_path: Path) -> dict[str, Any]:
    secret = settings.stripe_webhook_secret
    if not secret:
        return {"ok": False, "step": "stripe-sig", "error": "stripe_webhook_secret_not_configured"}
    payload = payload_path.read_bytes()
    ts = int(time.time())
    signed = f"{ts}.".encode() + payload
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {
        "ok": True,
        "step": "stripe-sig",
        "header": f"t={ts},v1={signature}",
    }


# ---------------------------------------------------------------------------
# verify-paid
# ---------------------------------------------------------------------------


async def verify_paid(context_path: Path) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        payment = (
            await db.execute(
                select(CallPayment)
                .where(CallPayment.contact_id == PROSPECT_CONTACT_ID)
                .order_by(CallPayment.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if payment is None:
        return {"ok": False, "step": "verify-paid", "error": "call_payment_not_found"}

    checks = {
        "status_paid": payment.status == CallPaymentStatus.PAID,
        "paid_at_set": payment.paid_at is not None,
        "payment_intent_recorded": payment.stripe_payment_intent_id == STUB_PAYMENT_INTENT_ID,
        "operators_notified": payment.operators_notified_at is not None,
    }
    return {
        "ok": all(checks.values()),
        "step": "verify-paid",
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": float(payment.amount),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "seed":
            result = await seed(Path(args.artifacts_dir))
        elif args.command == "first-touch":
            result = await first_touch()
        elif args.command == "verify-inbound":
            result = await verify_inbound(Path(args.context))
        elif args.command == "ai-reply":
            result = await ai_reply(Path(args.context))
        elif args.command == "close":
            result = await close(Path(args.artifacts_dir))
        elif args.command == "verify-paid":
            result = await verify_paid(Path(args.context))
        else:  # pragma: no cover - argparse guards
            _print({"ok": False, "error": f"unknown command {args.command}"})
            return 2
    finally:
        await engine.dispose()

    _print(result)
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Prestyj sales full-pipeline E2E smoke")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_p = sub.add_parser("seed", help="Ensure workspace + synthetic prospect; write artifacts")
    seed_p.add_argument("--artifacts-dir", required=True)

    sub.add_parser("first-touch", help="Autopilot outbound first-touch through a stub relay")

    vi = sub.add_parser("verify-inbound", help="Assert the replayed inbound reply landed")
    vi.add_argument("--context", required=True)

    ar = sub.add_parser("ai-reply", help="Drive the AI sales responder (deterministic draft)")
    ar.add_argument("--context", required=True)

    close_p = sub.add_parser("close", help="Run the close tool: Stripe link + iMessage")
    close_p.add_argument("--artifacts-dir", required=True)

    sig_p = sub.add_parser("stripe-sig", help="Compute a Stripe-Signature header for a payload")
    sig_p.add_argument("--payload", required=True)

    vp = sub.add_parser("verify-paid", help="Assert the CallPayment was marked paid")
    vp.add_argument("--context", required=True)

    args = parser.parse_args()

    if args.command == "stripe-sig":
        result = stripe_sig(Path(args.payload))
        _print(result)
        return 0 if result.get("ok") else 1

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
