"""SMS fallback service for voice campaigns.

The voice worker sends at most three spaced, consent-checked SMS touches
between unanswered call attempts (1, 3, and 5).
"""

import contextlib
import re
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    OutboundDeliveryResult,
    OutboundDeliveryStatus,
    outbound_delivery_service,
)

logger = structlog.get_logger()


async def send_sms_fallback(
    db: AsyncSession,
    campaign: Campaign,
    campaign_contact: CampaignContact,
    contact: Contact,
    call_outcome: str,
    telnyx_api_key: str,
) -> bool:
    """Send SMS fallback after call failure.

    Args:
        db: Database session
        campaign: The voice campaign
        campaign_contact: Campaign contact record
        contact: Contact record
        call_outcome: Why the call failed (no_answer, busy, voicemail)
        telnyx_api_key: Telnyx API key

    Returns:
        True if SMS was sent successfully
    """
    log = logger.bind(
        campaign_id=str(campaign.id),
        contact_id=contact.id,
        call_outcome=call_outcome,
    )

    if not campaign.sms_fallback_enabled:
        log.info("sms_fallback_disabled")
        return False

    if (
        campaign_contact.sms_fallback_sent_at
        and campaign_contact.last_call_at
        and campaign_contact.sms_fallback_sent_at >= campaign_contact.last_call_at
    ):
        log.info("sms_fallback_already_sent_for_attempt")
        return False

    # Determine message content
    message_text = None

    if campaign.sms_fallback_use_ai and campaign.sms_fallback_agent_id:
        # Generate AI message based on context
        try:
            from app.services.campaigns.ai_fallback import generate_sms_fallback_message

            message_text = await generate_sms_fallback_message(
                db=db,
                campaign=campaign,
                contact=contact,
                call_outcome=call_outcome,
            )
        except Exception as e:
            log.exception("ai_fallback_generation_failed", error=str(e))
            # Fall back to template if AI fails
            if campaign.sms_fallback_template:
                message_text = render_fallback_template(
                    campaign.sms_fallback_template,
                    contact,
                    call_outcome,
                )

    elif campaign.sms_fallback_template:
        # Use template
        message_text = render_fallback_template(
            campaign.sms_fallback_template,
            contact,
            call_outcome,
        )

    if not message_text:
        log.warning("no_fallback_message_configured")
        return False

    try:
        result = await outbound_delivery_service.deliver(
            db,
            OutboundDeliveryRequest(
                workspace_id=campaign.workspace_id,
                channel=OutboundDeliveryChannel.SMS,
                to=contact.phone_number,
                from_=campaign.from_phone_number,
                body=message_text,
                contact=contact,
                campaign=campaign,
                campaign_contact=campaign_contact,
                agent_id=campaign.sms_fallback_agent_id or campaign.agent_id,
                idempotency_scope="voice_campaign_sms_fallback",
                idempotency_parts=(campaign_contact.id, campaign_contact.call_attempts),
                action_type="voice_campaign_sms_fallback",
                require_sms_consent=True,
                metadata={"telnyx_api_key_configured": bool(telnyx_api_key)},
            ),
        )

        failed_reason = _sms_fallback_failure_reason(result)
        if failed_reason is not None:
            campaign_contact.last_error = failed_reason
            await db.commit()
            return False

        message = result.message
        assert message is not None

        # Update campaign contact
        campaign_contact.sms_fallback_sent = True
        campaign_contact.sms_fallback_sent_at = datetime.now(UTC)
        campaign_contact.sms_fallback_message_id = message.id
        if campaign_contact.status == CampaignContactStatus.CALL_FAILED:
            campaign_contact.status = CampaignContactStatus.SMS_FALLBACK_SENT
        campaign_contact.conversation_id = message.conversation_id
        campaign_contact.messages_sent += 1

        # Update campaign stats
        campaign.sms_fallbacks_sent += 1
        campaign.messages_sent += 1

        await db.commit()

        log.info("sms_fallback_sent", message_id=str(message.id))
        return True

    except Exception as e:
        log.exception("sms_fallback_failed", error=str(e))
        campaign_contact.last_error = f"SMS fallback failed: {e}"
        await db.commit()
        return False


def _sms_fallback_failure_reason(result: OutboundDeliveryResult) -> str | None:
    if result.status is OutboundDeliveryStatus.BLOCKED:
        return f"SMS fallback blocked: {result.reason}"
    if not result.delivered or result.message is None:
        return f"SMS fallback failed: {result.reason or 'provider_failed'}"
    return None


def render_fallback_template(
    template: str,
    contact: Contact,
    call_outcome: str,
) -> str:
    """Render SMS fallback template with contact data.

    Args:
        template: Message template with {placeholder} variables
        contact: Contact object with data to interpolate
        call_outcome: Why the call failed

    Returns:
        Rendered message with all placeholders replaced
    """
    full_name = " ".join(filter(None, [contact.first_name, contact.last_name])) or ""

    # Map call outcomes to friendly text
    outcome_text_map = {
        "no_answer": "we tried calling but couldn't reach you",
        "busy": "your line was busy when we called",
        "voicemail": "we left a message but wanted to follow up",
        "rejected": "we tried calling earlier",
    }
    call_reason = outcome_text_map.get(call_outcome, "we tried reaching you by phone")

    replacements: dict[str, str] = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "full_name": full_name,
        "company_name": contact.company_name or "",
        "email": contact.email or "",
        "call_outcome": call_outcome,
        "call_reason": call_reason,
    }

    message = template
    for placeholder, value in replacements.items():
        with contextlib.suppress(Exception):
            # Find placeholder pattern case-insensitively and replace with literal value
            pattern = re.compile(rf"\{{{placeholder}\}}", re.IGNORECASE)
            message = pattern.sub(value, message)

    return message
