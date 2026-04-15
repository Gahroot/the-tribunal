"""Resend webhook endpoint."""

import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DB
from app.api.webhooks.resend_handlers import handle_event
from app.core.config import settings

try:
    from svix.webhooks import Webhook, WebhookVerificationError

    SVIX_AVAILABLE = True
except ImportError:
    SVIX_AVAILABLE = False

router = APIRouter()
logger = structlog.get_logger()


def _verify_signature(
    payload: bytes, headers: dict[str, str]
) -> dict[str, Any]:
    """Verify the Svix signature on a Resend webhook and return the parsed event."""
    secret = settings.resend_webhook_secret

    if not secret:
        logger.warning("resend_webhook_secret_not_configured")
        parsed: dict[str, Any] = json.loads(payload)
        return parsed

    if not SVIX_AVAILABLE:
        logger.error("svix_not_installed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="svix package not installed",
        )

    try:
        wh = Webhook(secret)
        verified = wh.verify(payload, headers)
    except WebhookVerificationError as exc:
        logger.warning("resend_webhook_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from exc

    if isinstance(verified, dict):
        return verified
    fallback: dict[str, Any] = json.loads(payload)
    return fallback


@router.post("")
async def resend_webhook(request: Request, db: DB) -> dict[str, str]:
    """Handle incoming Resend webhook events (email.sent, email.delivered, etc.)."""
    log = logger.bind(endpoint="resend_webhook")
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    event = _verify_signature(body, headers)
    log = log.bind(event_type=event.get("type"))
    log.info("resend_webhook_received")

    await handle_event(db, event, log)
    return {"status": "ok"}
