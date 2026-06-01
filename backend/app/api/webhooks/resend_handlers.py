"""Compatibility wrappers for Resend webhook domain handling."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.webhooks.resend import (
    check_resend_idempotency,
    dispatch_resend_event,
    parse_resend_event,
)

logger = structlog.get_logger()


async def handle_event(
    db: AsyncSession,
    event: dict[str, Any],
    log: Any = None,
    provider_event_id: str | None = None,
) -> None:
    """Process a verified Resend webhook event.

    Kept for older tests/imports while the HTTP router now runs through the
    reusable webhook pipeline. New code should call the service-level parser,
    idempotency checker, and dispatcher directly.
    """
    bound_log = log or logger
    parsed = parse_resend_event(event, provider_event_id=provider_event_id)
    decision = await check_resend_idempotency(db, parsed, bound_log)
    if not decision.should_process:
        return
    await dispatch_resend_event(db, parsed, bound_log)
