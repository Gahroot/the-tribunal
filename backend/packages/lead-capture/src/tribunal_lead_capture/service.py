"""Delivery helpers for public lead magnet opt-ins.

This is the block's public service surface: ``deliver_lead_magnet_to_lead`` is
called by the offers block when an offer opt-in captures a ``LeadMagnetLead``.
The actual email send goes through the shared ``app.services.email`` (Resend)
integration — a cross-block dependency documented in the block README.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email import customer_email_brand_name, send_automation_email
from app.services.integration_credentials import IntegrationCredentialError

from .models import LeadMagnet, LeadMagnetLead

logger = structlog.get_logger()

_FAILURE_NO_EMAIL = "No email address was provided for lead magnet delivery."
_FAILURE_NO_CONTENT = "Lead magnet has no delivery link or content configured."
_FAILURE_PROVIDER = "Email delivery service did not accept the lead magnet email."


def _truncate_error(message: str) -> str:
    return message[:500]


def _format_content_data(content_data: dict[str, Any] | None) -> list[str]:
    """Return visitor-safe text snippets from a rich lead magnet payload."""
    if not content_data:
        return []

    lines: list[str] = []
    for key in ("title", "headline", "description", "summary", "content", "body"):
        value = content_data.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(value.strip())

    if not lines:
        lines.append("Your lead magnet content is included on the offer page.")

    return lines


def build_lead_magnet_email_body(
    *,
    lead_magnet: LeadMagnet,
    offer_name: str,
    recipient_name: str | None = None,
    brand_name: str = "The team",
) -> str:
    """Build the plain-text body sent through the shared automation email service."""
    greeting = (
        f"Hi {recipient_name.strip()},"
        if recipient_name and recipient_name.strip()
        else "Hi there,"
    )
    lines = [
        greeting,
        "",
        f"Thanks for signing up for {offer_name}. Here is your promised lead magnet:",
        f"{lead_magnet.name}",
    ]

    if lead_magnet.description:
        lines.extend(["", lead_magnet.description])

    if lead_magnet.content_url:
        lines.extend(["", "Access it here:", lead_magnet.content_url])
    else:
        content_lines = _format_content_data(lead_magnet.content_data)
        if content_lines:
            lines.extend(["", *content_lines])

    lines.extend(
        [
            "",
            "If you have any trouble accessing it, contact the business through the offer page.",
            "",
            f"— {brand_name}",
        ]
    )
    return "\n".join(lines)


async def deliver_lead_magnet_to_lead(
    *,
    lead: LeadMagnetLead,
    lead_magnet: LeadMagnet,
    offer_name: str,
    db: AsyncSession,
    workspace_id: uuid.UUID,
) -> bool:
    """Email one lead magnet and update the lead delivery fields in-place."""
    lead.delivery_attempted_at = datetime.now(UTC)
    lead.delivered = False
    lead.delivered_at = None

    if not lead.email:
        lead.delivery_error = _FAILURE_NO_EMAIL
        logger.warning(
            "lead_magnet_delivery_skipped_no_email",
            lead_magnet_lead_id=str(lead.id),
            lead_magnet_id=str(lead_magnet.id),
        )
        return False

    if not lead_magnet.content_url and not lead_magnet.content_data:
        lead.delivery_error = _FAILURE_NO_CONTENT
        logger.warning(
            "lead_magnet_delivery_skipped_no_content",
            lead_magnet_lead_id=str(lead.id),
            lead_magnet_id=str(lead_magnet.id),
        )
        return False

    try:
        if (
            lead.workspace_id != workspace_id
            or lead_magnet.workspace_id != workspace_id
            or lead.lead_magnet_id != lead_magnet.id
        ):
            raise IntegrationCredentialError("Lead magnet does not belong to this brand.")
        brand_name = await customer_email_brand_name(db, workspace_id)
    except IntegrationCredentialError as exc:
        lead.delivery_error = str(exc)
        return False

    subject = f"Your {lead_magnet.name}"
    body = build_lead_magnet_email_body(
        lead_magnet=lead_magnet,
        offer_name=offer_name,
        recipient_name=lead.name,
        brand_name=brand_name,
    )
    idempotency_key = lead.id if isinstance(lead.id, uuid.UUID) else None

    try:
        accepted = await send_automation_email(
            to_email=lead.email,
            subject=subject,
            body=body,
            db=db,
            workspace_id=workspace_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # pragma: no cover
        # send_automation_email normally catches provider errors; keep this as a hard guard.
        lead.delivery_error = _truncate_error(f"Lead magnet email delivery failed: {exc}")
        logger.exception(
            "lead_magnet_delivery_failed",
            lead_magnet_lead_id=str(lead.id),
            lead_magnet_id=str(lead_magnet.id),
        )
        return False

    if not accepted:
        lead.delivery_error = _FAILURE_PROVIDER
        logger.warning(
            "lead_magnet_delivery_rejected",
            lead_magnet_lead_id=str(lead.id),
            lead_magnet_id=str(lead_magnet.id),
            to_email=lead.email,
        )
        return False

    lead.delivered = True
    lead.delivered_at = datetime.now(UTC)
    lead.delivery_error = None
    logger.info(
        "lead_magnet_delivered",
        lead_magnet_lead_id=str(lead.id),
        lead_magnet_id=str(lead_magnet.id),
        to_email=lead.email,
    )
    return True
