"""Telnyx webhook endpoints for SMS and voice events.

This module is a thin dispatch layer: it verifies webhooks, parses payloads,
and routes events to handlers in ``telnyx_message_handlers`` (SMS/MMS) and
``telnyx_call_handlers`` (voice).
"""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Request

from app.api.webhooks.telnyx_call_handlers import (
    handle_call_answered,
    handle_call_hangup,
    handle_call_initiated,
    handle_machine_detection,
)
from app.api.webhooks.telnyx_message_handlers import (
    handle_delivery_status,
    handle_inbound_message,
)
from app.api.webhooks.telnyx_parser import verify_and_parse

router = APIRouter()
logger = structlog.get_logger()


EventHandler = Callable[[dict[str, Any], Any], Awaitable[None]]


_SMS_HANDLERS: dict[str, EventHandler] = {
    "message.received": handle_inbound_message,
    "message.sent": handle_delivery_status,
    "message.finalized": handle_delivery_status,
}


_VOICE_HANDLERS: dict[str, EventHandler] = {
    "call.initiated": handle_call_initiated,
    "call.answered": handle_call_answered,
    "call.hangup": handle_call_hangup,
    "call.machine.detection.ended": handle_machine_detection,
}


@router.post("/sms")
async def telnyx_sms_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Telnyx SMS webhooks.

    Telnyx sends webhooks for:
    - message.received: Inbound SMS received
    - message.sent: Outbound message sent
    - message.finalized: Final delivery status
    """
    log = logger.bind(endpoint="telnyx_sms_webhook")

    parsed = await verify_and_parse(request, log)
    if parsed is None:
        return {"status": "error", "message": "Invalid JSON"}

    event_type, event_payload = parsed
    log = log.bind(event_type=event_type)
    log.info("webhook_received")

    handler = _SMS_HANDLERS.get(event_type)
    if handler is not None:
        await handler(event_payload, log)
    else:
        log.debug("unhandled_event_type")

    return {"status": "ok"}


@router.post("/voice")
async def telnyx_voice_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Telnyx voice webhooks.

    Telnyx sends webhooks for:
    - call.initiated: Incoming call received
    - call.answered: Call was answered
    - call.hangup: Call ended
    - call.machine.detection.ended: Voicemail/human detection result
    """
    log = logger.bind(endpoint="telnyx_voice_webhook")

    parsed = await verify_and_parse(request, log)
    if parsed is None:
        return {"status": "error", "message": "Invalid JSON"}

    event_type, event_payload = parsed
    log = log.bind(event_type=event_type)
    log.info(
        "========== TELNYX VOICE WEBHOOK ==========",
        event_type=event_type,
        call_control_id=event_payload.get("call_control_id"),
        call_state=event_payload.get("state"),
        direction=event_payload.get("direction"),
    )

    handler = _VOICE_HANDLERS.get(event_type)
    if handler is not None:
        await handler(event_payload, log)
    else:
        log.info("unhandled_voice_event_type", event_type=event_type)

    return {"status": "ok"}
