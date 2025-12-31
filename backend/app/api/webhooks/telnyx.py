"""Telnyx webhook endpoints for SMS and voice events."""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.campaign import CampaignContact
from app.models.phone_number import PhoneNumber
from app.services.ai.text_agent import schedule_ai_response
from app.services.telephony.telnyx import TelnyxSMSService

router = APIRouter()
logger = structlog.get_logger()


@router.post("/sms")
async def telnyx_sms_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Telnyx SMS webhooks.

    Telnyx sends webhooks for:
    - message.received: Inbound SMS received
    - message.sent: Outbound message sent
    - message.finalized: Final delivery status
    """
    log = logger.bind(endpoint="telnyx_sms_webhook")

    try:
        payload = await request.json()
    except Exception:
        log.error("invalid_json_payload")
        return {"status": "error", "message": "Invalid JSON"}

    # Extract event data
    data = payload.get("data", {})
    event_type = data.get("event_type", "")
    event_payload = data.get("payload", {})

    log = log.bind(event_type=event_type)
    log.info("webhook_received")

    # Handle different event types
    if event_type == "message.received":
        await handle_inbound_message(event_payload, log)
    elif event_type in ("message.sent", "message.finalized"):
        await handle_delivery_status(event_payload, log)
    else:
        log.debug("unhandled_event_type")

    return {"status": "ok"}


async def handle_inbound_message(payload: dict[str, Any], log: Any) -> None:
    """Handle inbound SMS message.

    Args:
        payload: Telnyx message payload
        log: Logger instance
    """
    # Extract message details
    from_number = payload.get("from", {}).get("phone_number", "")
    to_number = payload.get("to", [{}])[0].get("phone_number", "")
    body = payload.get("text", "")
    message_id = payload.get("id", "")

    log = log.bind(
        from_number=from_number,
        to_number=to_number,
        message_id=message_id,
    )
    log.info("processing_inbound_sms")

    if not all([from_number, to_number, body]):
        log.warning("missing_required_fields")
        return

    async with AsyncSessionLocal() as db:
        # Look up workspace by phone number
        result = await db.execute(
            select(PhoneNumber).where(PhoneNumber.phone_number == to_number)
        )
        phone_record = result.scalar_one_or_none()

        if not phone_record:
            log.warning("phone_number_not_found", to_number=to_number)
            return

        workspace_id = phone_record.workspace_id

        # Process inbound message
        telnyx_api_key = settings.telnyx_api_key
        if not telnyx_api_key:
            log.error("no_telnyx_api_key")
            return

        sms_service = TelnyxSMSService(telnyx_api_key)
        try:
            message = await sms_service.process_inbound_message(
                db=db,
                provider_message_id=message_id,
                from_number=from_number,
                to_number=to_number,
                body=body,
                workspace_id=workspace_id,
            )

            # Schedule AI response with debounce
            if message.conversation_id:
                # Get conversation to check if AI is enabled
                from app.models.conversation import Conversation
                conv_result = await db.execute(
                    select(Conversation).where(Conversation.id == message.conversation_id)
                )
                conversation = conv_result.scalar_one_or_none()

                if conversation:
                    # Check if conversation is part of a campaign and assign campaign agent
                    if not conversation.assigned_agent_id:
                        campaign_contact_result = await db.execute(
                            select(CampaignContact)
                            .options(selectinload(CampaignContact.campaign))
                            .where(CampaignContact.conversation_id == conversation.id)
                        )
                        campaign_contact = campaign_contact_result.scalar_one_or_none()

                        if campaign_contact and campaign_contact.campaign and campaign_contact.campaign.agent_id:
                            # Assign campaign's agent to the conversation
                            conversation.assigned_agent_id = campaign_contact.campaign.agent_id
                            conversation.ai_enabled = True
                            log.info(
                                "assigned_campaign_agent",
                                conversation_id=str(conversation.id),
                                campaign_id=str(campaign_contact.campaign_id),
                                agent_id=str(campaign_contact.campaign.agent_id),
                            )
                            await db.commit()
                            await db.refresh(conversation)

                    if conversation.ai_enabled and not conversation.ai_paused:
                        # Use agent's delay setting or default
                        delay_ms = settings.ai_response_delay_ms
                        if conversation.assigned_agent_id:
                            from app.models.agent import Agent
                            agent_result = await db.execute(
                                select(Agent).where(Agent.id == conversation.assigned_agent_id)
                            )
                            agent = agent_result.scalar_one_or_none()
                            if agent:
                                delay_ms = agent.text_response_delay_ms

                        await schedule_ai_response(
                            conversation_id=message.conversation_id,
                            workspace_id=workspace_id,
                            delay_ms=delay_ms,
                        )

            log.info("inbound_sms_processed", message_id=str(message.id))
        finally:
            await sms_service.close()


async def handle_delivery_status(payload: dict[str, Any], log: Any) -> None:
    """Handle delivery status update.

    Args:
        payload: Telnyx status payload
        log: Logger instance
    """
    message_id = payload.get("id", "")
    to_info = payload.get("to", [{}])[0] if payload.get("to") else {}
    status = to_info.get("status", "unknown")

    log = log.bind(message_id=message_id, status=status)
    log.info("processing_delivery_status")

    async with AsyncSessionLocal() as db:
        telnyx_api_key = settings.telnyx_api_key
        if not telnyx_api_key:
            log.error("no_telnyx_api_key")
            return

        sms_service = TelnyxSMSService(telnyx_api_key)
        try:
            await sms_service.update_message_status(
                db=db,
                provider_message_id=message_id,
                status=status,
            )
        finally:
            await sms_service.close()


@router.post("/voice")
async def telnyx_voice_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Telnyx voice webhooks.

    TODO: Implement voice call handling with OpenAI Realtime.
    """
    log = logger.bind(endpoint="telnyx_voice_webhook")
    log.info("voice_webhook_received")

    # Voice handling will be implemented in Phase 4
    return {"status": "ok"}
