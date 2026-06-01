"""Resend webhook endpoint."""

import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DB
from app.core.config import settings
from app.services.webhooks.pipeline import WebhookPipeline, WebhookRequestEnvelope
from app.services.webhooks.resend import (
    RESEND_PROVIDER,
    ResendWebhookEvent,
    check_resend_idempotency,
    dispatch_resend_event,
    parse_resend_event,
)

try:
    from svix.webhooks import Webhook, WebhookVerificationError

    SVIX_AVAILABLE = True
except ImportError:
    SVIX_AVAILABLE = False

router = APIRouter()
logger = structlog.get_logger()


async def _verify_resend_envelope(envelope: WebhookRequestEnvelope) -> dict[str, Any]:
    """Verify the Svix signature on a Resend webhook and return the parsed event."""
    return _verify_signature(envelope.raw_body, dict(envelope.headers))


def _parse_resend_payload(
    payload: dict[str, Any],
    envelope: WebhookRequestEnvelope,
) -> ResendWebhookEvent:
    provider_event_id = envelope.headers.get("svix-id") or envelope.headers.get("webhook-id")
    return parse_resend_event(payload, provider_event_id=provider_event_id)


_RESEND_PIPELINE = WebhookPipeline[dict[str, Any], ResendWebhookEvent](
    provider=RESEND_PROVIDER,
    verifier=_verify_resend_envelope,
    parser=_parse_resend_payload,
    idempotency_checker=check_resend_idempotency,
    dispatcher=dispatch_resend_event,
)


def _verify_signature(payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
    """Verify the Svix signature on a Resend webhook and return the parsed event."""
    secret = settings.resend_webhook_secret

    if not secret:
        logger.warning("resend_webhook_secret_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured.",
        )

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
    parsed: dict[str, Any] = json.loads(payload)
    return parsed


@router.post("")
async def resend_webhook(request: Request, db: DB) -> dict[str, str]:
    """Handle incoming Resend webhook events (email.sent, email.delivered, etc.)."""
    envelope = WebhookRequestEnvelope(
        provider=RESEND_PROVIDER,
        raw_body=await request.body(),
        headers={k.lower(): v for k, v in request.headers.items()},
    )
    result = await _RESEND_PIPELINE.process(
        db=db,
        request=envelope,
        log=logger.bind(endpoint="resend_webhook"),
    )
    return result.response_body()
