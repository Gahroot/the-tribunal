"""Cal.com webhook endpoints for appointment events.

This module is a thin FastAPI router. All real work is delegated:

- :mod:`app.api.webhooks.calcom_parser` — payload parsing / contact lookup
- :mod:`app.api.webhooks.calcom_events` — lifecycle SMS + downstream dispatch
- :mod:`app.api.webhooks.calcom_handlers` — per-event state-machine handlers
"""

from typing import Any

import structlog
from fastapi import APIRouter, Request

from app.api.webhooks.calcom_handlers import (
    handle_booking_cancelled,
    handle_booking_created,
    handle_booking_rescheduled,
    handle_meeting_ended,
)
from app.core.webhook_security import verify_calcom_webhook

router = APIRouter()
logger = structlog.get_logger()


# Dispatch table keyed by Cal.com ``trigger`` field.
# Using a dict avoids a long if/elif chain (ruff PLR0911/PLR0912) and keeps
# the router trivially extensible.
_EVENT_DISPATCH: dict[str, Any] = {
    "BOOKING_CREATED": handle_booking_created,
    "BOOKING_RESCHEDULED": handle_booking_rescheduled,
    "BOOKING_CANCELLED": handle_booking_cancelled,
    "MEETING_ENDED": handle_meeting_ended,
}


@router.post("/booking")
async def calcom_booking_webhook(request: Request) -> dict[str, str]:
    """Handle Cal.com booking events.

    Cal.com sends webhooks for:
    - ``BOOKING_CREATED``: New booking created
    - ``BOOKING_RESCHEDULED``: Booking rescheduled
    - ``BOOKING_CANCELLED``: Booking cancelled
    - ``MEETING_ENDED``: Meeting completed (or marked no-show)

    All webhooks are signature-verified before processing.
    """
    log = logger.bind(endpoint="calcom_booking_webhook")

    try:
        await verify_calcom_webhook(request)
    except Exception as e:
        log.error("webhook_verification_failed", error=str(e))
        raise

    try:
        payload = await request.json()
    except Exception as e:
        log.error("invalid_json_payload", error=str(e))
        return {"status": "error", "message": "Invalid JSON"}

    trigger = payload.get("trigger", "")
    data = payload.get("data", {})

    log = log.bind(event_type=trigger)
    log.info("webhook_received")

    handler = _EVENT_DISPATCH.get(trigger)
    if handler is None:
        log.debug("unhandled_event_type")
    else:
        await handler(data, log)

    return {"status": "ok"}
