#!/usr/bin/env python3
"""iMessage channel bidirectional smoke check (Python orchestrator).

The Tribunal's full sales autonomy rides on the self-hosted Mac iMessage relay
working in BOTH directions. This script proves that path end to end against a
local backend + the shared local Postgres:

    outbound:  app code -> MacRelayMessageService -> relay HTTP POST /v1/messages
    inbound:   relay webhook -> /webhooks/mac-relay/messages -> Conversation +
               AI responder scheduling

It is split into subcommands so the shell wrapper
(``scripts/dev/imessage_channel_smoke.sh``) can orchestrate the live pieces
(``http.sh`` for the webhook replay, ``logs.sh`` for the responder proof):

    seed            Idempotently create a dedicated smoke workspace, sender
                    identity (PhoneNumber + mac_relay_sender_id), agent, and
                    contact. Writes ``payload.json`` (inbound webhook body) and
                    ``context.json`` (ids + webhook token) into --artifacts-dir.
    outbound        Spin up an in-process stub relay, send an outbound iMessage
                    through the real outbound delivery stack pointed at the
                    stub, and assert the relay received it + a Message persisted.
    verify-inbound  After the webhook has been replayed, assert the inbound
                    Message landed on the right Conversation with AI enabled.

Every subcommand prints a single-line JSON result to stdout (``{"ok": true,
...}``) and exits non-zero on failure so the shell can gate on it.

Run from the backend directory so pydantic loads ``backend/.env``:

    cd backend && uv run python ../scripts/dev/imessage_channel_smoke.py seed \\
        --artifacts-dir ../.ezcoder/eyes/out/imessage-smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.encryption import hash_phone, hash_value
from app.db.session import AsyncSessionLocal, engine
from app.models.agent import Agent
from app.models.contact import Contact
from app.models.conversation import Conversation, Message, MessageChannel, MessageDirection
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    outbound_delivery_service,
)
from app.utils.phone import normalize_phone_e164

# Keep stdout machine-parseable: the only thing we emit there is the JSON
# result line. ``DEBUG=true`` in backend/.env turns on SQLAlchemy echo, so mute
# it (and asyncpg) to WARNING for this CLI.
for _noisy in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Deterministic identities so the check is repeatable and never collides with
# real CRM data. The sender is an Apple ID-style address (relay senders may be
# emails) and the contact phone is a clean E.164 reserved-style number.
WORKSPACE_SLUG = "imessage-smoke"
WORKSPACE_NAME = "iMessage Smoke Workspace"
AGENT_NAME = "iMessage Smoke Agent"
# The relay addresses the workspace by its sender identity. We use a phone-style
# identity (not an Apple ID email) because ``conversations.workspace_phone`` is
# ``VARCHAR(20)`` and an email overflows it.
SENDER_PHONE = "+12025550181"
SENDER_ADDRESS = SENDER_PHONE
CONTACT_PHONE = "+14155550123"
CONTACT_FIRST = "Smoke"
CONTACT_LAST = "Lead"
OUTBOUND_BODY = "Hey! Quick one - which batch size are you weighing up? (100/300/500/1000)"
INBOUND_BODY = "Interested. How much for 100 video ads?"


def _print(result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


async def _get_or_create_workspace(db: Any) -> Workspace:
    existing = (
        await db.execute(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    ws = Workspace(
        id=uuid.uuid4(),
        name=WORKSPACE_NAME,
        slug=WORKSPACE_SLUG,
        description="Dedicated workspace for the iMessage channel smoke check.",
        settings={"timezone": "America/New_York"},
        is_active=True,
    )
    db.add(ws)
    await db.flush()
    return ws


async def _get_or_create_agent(db: Any, workspace_id: uuid.UUID) -> Agent:
    existing = (
        await db.execute(
            select(Agent).where(
                Agent.workspace_id == workspace_id,
                Agent.name == AGENT_NAME,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=AGENT_NAME,
        description="Closes Prestyj Batch Video Ads packs over iMessage.",
        channel_mode="both",
        voice_provider="openai",
        voice_id="alloy",
        language="en-US",
        system_prompt=(
            "You sell Prestyj Batch Video Ads packs over iMessage. Anchor on the "
            "500 pack, close to Stripe payment, escalate only for add-ons."
        ),
        temperature=0.7,
        max_tokens=2000,
        initial_greeting="Hey - thanks for reaching out about batch video ads!",
        is_active=True,
    )
    db.add(agent)
    await db.flush()
    return agent


async def _get_or_create_phone(
    db: Any, workspace_id: uuid.UUID, agent_id: uuid.UUID
) -> PhoneNumber:
    existing = (
        await db.execute(select(PhoneNumber).where(PhoneNumber.phone_number == SENDER_PHONE))
    ).scalar_one_or_none()
    if existing is not None:
        # Keep the sender wired to the smoke agent and active across re-runs.
        existing.workspace_id = workspace_id
        existing.mac_relay_sender_id = SENDER_ADDRESS
        existing.assigned_agent_id = agent_id
        existing.is_active = True
        existing.imessage_enabled = True
        await db.flush()
        return existing
    phone = PhoneNumber(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        phone_number=SENDER_PHONE,
        friendly_name="iMessage Smoke Sender",
        mac_relay_sender_id=SENDER_ADDRESS,
        sms_enabled=True,
        voice_enabled=False,
        imessage_enabled=True,
        mac_relay_service="imessage",
        assigned_agent_id=agent_id,
        is_active=True,
    )
    db.add(phone)
    await db.flush()
    return phone


async def _get_or_create_contact(db: Any, workspace_id: uuid.UUID) -> Contact:
    phone_hash = hash_phone(CONTACT_PHONE)
    existing = (
        await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.phone_hash == phone_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    email = "smoke-lead@imessage.test"
    contact = Contact(
        workspace_id=workspace_id,
        first_name=CONTACT_FIRST,
        last_name=CONTACT_LAST,
        email=email,
        email_hash=hash_value(email),
        phone_number=CONTACT_PHONE,
        phone_hash=phone_hash,
        company_name="Smoke Realty",
        status="new",
    )
    db.add(contact)
    await db.flush()
    return contact


async def seed(artifacts_dir: Path) -> dict[str, Any]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    inbound_guid = f"smoke-{uuid.uuid4()}"
    inbound_provider_message_id = f"mac-relay:{inbound_guid}"
    normalized_contact = normalize_phone_e164(CONTACT_PHONE)

    async with AsyncSessionLocal() as db:
        workspace = await _get_or_create_workspace(db)
        agent = await _get_or_create_agent(db, workspace.id)
        phone = await _get_or_create_phone(db, workspace.id, agent.id)
        contact = await _get_or_create_contact(db, workspace.id)
        await db.commit()
        workspace_id = str(workspace.id)
        agent_id = str(agent.id)
        phone_id = str(phone.id)
        contact_id = contact.id

    # Inbound webhook body (minimal but realistic relay event). The relay
    # addresses the workspace by the sender identity it delivered from.
    payload = {
        "event_id": inbound_guid,
        "guid": inbound_guid,
        "from": CONTACT_PHONE,
        "to": SENDER_ADDRESS,
        "text": INBOUND_BODY,
        "is_from_me": False,
        "service": "imessage",
    }
    payload_path = artifacts_dir / "payload.json"
    payload_path.write_text(json.dumps(payload, indent=2) + "\n")

    webhook_token = settings.mac_relay_webhook_token or settings.mac_relay_token
    context = {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "phone_number_id": phone_id,
        "contact_id": contact_id,
        "sender": SENDER_ADDRESS,
        "contact_phone": CONTACT_PHONE,
        "normalized_contact_phone": normalized_contact,
        "outbound_body": OUTBOUND_BODY,
        "inbound_guid": inbound_guid,
        "inbound_provider_message_id": inbound_provider_message_id,
        "webhook_token": webhook_token,
        "mac_relay_token": settings.mac_relay_token,
        "payload_path": str(payload_path),
    }
    context_path = artifacts_dir / "context.json"
    context_path.write_text(json.dumps(context, indent=2) + "\n")

    return {
        "ok": True,
        "step": "seed",
        "workspace_id": workspace_id,
        "sender": SENDER_ADDRESS,
        "contact_phone": CONTACT_PHONE,
        "inbound_provider_message_id": inbound_provider_message_id,
        "payload_path": str(payload_path),
        "context_path": str(context_path),
        "webhook_token_present": bool(webhook_token),
    }


# ---------------------------------------------------------------------------
# outbound
# ---------------------------------------------------------------------------


class _StubRelayState:
    """Captures the last outbound request the stub relay received."""

    def __init__(self) -> None:
        self.last_payload: dict[str, Any] | None = None
        self.request_count = 0


def _make_stub_handler(state: _StubRelayState, token: str) -> type[BaseHTTPRequestHandler]:
    class StubRelayHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:  # silence stderr noise
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
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                self._json(401, {"error": "unauthorized"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                payload = {}
            state.last_payload = payload
            state.request_count += 1
            self._json(
                200,
                {"id": payload.get("client_message_id") or str(uuid.uuid4()), "status": "sent"},
            )

    return StubRelayHandler


async def outbound() -> dict[str, Any]:
    state = _StubRelayState()
    token = settings.mac_relay_token or "smoke-relay-token"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_stub_handler(state, token))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Point the (process-local) settings at the stub relay so the real
    # outbound delivery stack selects MacRelayMessageService and POSTs to it.
    original_base_url = settings.mac_relay_base_url
    original_provider = settings.text_message_provider
    original_token = settings.mac_relay_token
    settings.mac_relay_base_url = f"http://127.0.0.1:{port}"
    settings.mac_relay_token = token
    settings.text_message_provider = "mac_relay"

    try:
        async with AsyncSessionLocal() as db:
            workspace = (
                await db.execute(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
            ).scalar_one_or_none()
            if workspace is None:
                return {"ok": False, "step": "outbound", "error": "workspace_not_seeded"}
            phone = (
                await db.execute(
                    select(PhoneNumber).where(PhoneNumber.mac_relay_sender_id == SENDER_ADDRESS)
                )
            ).scalar_one_or_none()

            request = OutboundDeliveryRequest(
                workspace_id=workspace.id,
                channel=OutboundDeliveryChannel.IMESSAGE,
                to=CONTACT_PHONE,
                from_=SENDER_ADDRESS,
                body=OUTBOUND_BODY,
                agent_id=phone.assigned_agent_id if phone else None,
                phone_number_id=phone.id if phone else None,
                action_type="imessage_smoke_outbound",
            )
            result = await outbound_delivery_service.deliver(db, request)
    finally:
        settings.mac_relay_base_url = original_base_url
        settings.text_message_provider = original_provider
        settings.mac_relay_token = original_token
        server.shutdown()
        server.server_close()

    checks: dict[str, bool] = {
        "delivery_sent": result.delivered,
        "relay_received_request": state.request_count >= 1,
        "provider_is_mac_relay": (result.provider or "").lower() in {"mac_relay", "imessage"},
        "provider_message_id_prefixed": bool(
            result.provider_message_id and result.provider_message_id.startswith("mac-relay:")
        ),
        "message_persisted": result.message is not None,
        "channel_is_imessage": result.message is not None
        and result.message.channel == MessageChannel.IMESSAGE,
        "direction_outbound": result.message is not None
        and result.message.direction
        in {MessageDirection.OUTBOUND, MessageDirection.OUTBOUND.value, "outbound"},
    }
    relay_payload = state.last_payload or {}
    checks["relay_text_matches"] = relay_payload.get("text") == OUTBOUND_BODY
    checks["relay_service_imessage"] = relay_payload.get("service") == "imessage"
    checks["relay_from_matches"] = relay_payload.get("from") == SENDER_ADDRESS

    ok = all(checks.values())
    return {
        "ok": ok,
        "step": "outbound",
        "status": result.status.value,
        "provider": result.provider,
        "provider_message_id": result.provider_message_id,
        "reason": result.reason,
        "relay_request_count": state.request_count,
        "relay_payload": relay_payload,
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
    expected_contact = context.get("normalized_contact_phone") or context["contact_phone"]

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
        "conversation_ai_enabled": bool(conversation.ai_enabled),
        "conversation_ai_not_paused": not bool(conversation.ai_paused),
        "conversation_has_agent": conversation.assigned_agent_id is not None,
    }
    ok = all(checks.values())
    return {
        "ok": ok,
        "step": "verify-inbound",
        "message_id": str(message.id),
        "conversation_id": str(conversation.id),
        "workspace_phone": conversation.workspace_phone,
        "contact_phone": conversation.contact_phone,
        "assigned_agent_id": str(conversation.assigned_agent_id)
        if conversation.assigned_agent_id
        else None,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "seed":
            result = await seed(Path(args.artifacts_dir))
        elif args.command == "outbound":
            result = await outbound()
        elif args.command == "verify-inbound":
            result = await verify_inbound(Path(args.context))
        else:  # pragma: no cover - argparse guards this
            _print({"ok": False, "error": f"unknown command {args.command}"})
            return 2
    finally:
        await engine.dispose()

    _print(result)
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="iMessage channel bidirectional smoke check")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_p = sub.add_parser("seed", help="Seed workspace/sender/agent/contact + write artifacts")
    seed_p.add_argument("--artifacts-dir", required=True)

    sub.add_parser("outbound", help="Send an outbound iMessage through a stub relay and assert")

    verify_p = sub.add_parser("verify-inbound", help="Assert the replayed inbound message landed")
    verify_p.add_argument("--context", required=True, help="Path to context.json from seed")

    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
