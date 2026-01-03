"""Telnyx webhook endpoints for SMS and voice events."""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.webhook_security import verify_telnyx_webhook
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
    await verify_telnyx_webhook(request)

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

                        if (
                            campaign_contact
                            and campaign_contact.campaign
                            and campaign_contact.campaign.agent_id
                        ):
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

    Telnyx sends webhooks for:
    - call.initiated: Incoming call received
    - call.answered: Call was answered
    - call.hangup: Call ended
    - call.machine.detection.ended: Voicemail/human detection result
    """
    await verify_telnyx_webhook(request)

    log = logger.bind(endpoint="telnyx_voice_webhook")

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
    if event_type == "call.initiated":
        await handle_call_initiated(event_payload, log)
    elif event_type == "call.answered":
        await handle_call_answered(event_payload, log)
    elif event_type == "call.hangup":
        await handle_call_hangup(event_payload, log)
    elif event_type == "call.machine.detection.ended":
        await handle_machine_detection(event_payload, log)
    else:
        log.debug("unhandled_event_type")

    return {"status": "ok"}


async def handle_call_initiated(payload: dict[Any, Any], log: Any) -> None:
    """Handle incoming call.

    Args:
        payload: Telnyx call event payload
        log: Logger instance
    """
    call_control_id = payload.get("call_control_id", "")
    from_number = payload.get("from", {}).get("phone_number", "")
    to_number = payload.get("to", [{}])[0].get("phone_number", "")
    call_state = payload.get("state", "")

    log = log.bind(
        call_control_id=call_control_id,
        from_number=from_number,
        to_number=to_number,
        call_state=call_state,
    )
    log.info("processing_call_initiated")

    if not all([call_control_id, from_number, to_number]):
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

        # Create message record for incoming call
        from app.models.conversation import Conversation

        # Get or create conversation
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.workspace_phone == to_number,
                Conversation.contact_phone == from_number,
            )
        )
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            from app.models.contact import Contact

            # Try to find contact
            contact_result = await db.execute(
                select(Contact).where(
                    Contact.workspace_id == workspace_id,
                    Contact.phone_number == from_number,
                )
            )
            contact = contact_result.scalar_one_or_none()

            conversation = Conversation(
                workspace_id=workspace_id,
                contact_id=contact.id if contact else None,
                workspace_phone=to_number,
                contact_phone=from_number,
                channel="voice",
                ai_enabled=True,
            )
            db.add(conversation)
            await db.flush()

        # Create inbound message
        from app.models.conversation import Message

        message = Message(
            conversation_id=conversation.id,
            provider_message_id=call_control_id,
            direction="inbound",
            channel="voice",
            body="",  # Voice calls don't have body
            status="ringing",
        )
        db.add(message)

        # Update conversation
        conversation.channel = "voice"
        conversation.last_message_preview = "Incoming call"
        conversation.last_message_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(message)

        log.info("call_initiated_processed", message_id=str(message.id))

        # Auto-answer calls if phone number has an assigned active agent
        await auto_answer_call_if_agent_assigned(
            call_control_id=call_control_id,
            phone_record=phone_record,
            conversation=conversation,
            log=log,
        )


async def handle_call_answered(payload: dict[Any, Any], log: Any) -> None:
    """Handle call answered event.

    Args:
        payload: Telnyx call event payload
        log: Logger instance
    """
    call_control_id = payload.get("call_control_id", "")
    call_state = payload.get("state", "")

    log = log.bind(call_control_id=call_control_id, call_state=call_state)
    log.info("call_answered")

    async with AsyncSessionLocal() as db:
        from app.models.conversation import Message

        result = await db.execute(
            select(Message).where(
                Message.provider_message_id == call_control_id
            )
        )
        message = result.scalar_one_or_none()

        if message:
            message.status = "answered"
            await db.commit()
            log.info("message_updated", message_id=str(message.id))


async def handle_call_hangup(payload: dict[Any, Any], log: Any) -> None:
    """Handle call hangup event.

    Args:
        payload: Telnyx call event payload
        log: Logger instance
    """
    call_control_id = payload.get("call_control_id", "")
    call_state = payload.get("state", "")
    duration_secs = payload.get("duration_seconds", 0)

    log = log.bind(
        call_control_id=call_control_id,
        call_state=call_state,
        duration=duration_secs,
    )
    log.info("call_hangup")

    async with AsyncSessionLocal() as db:
        from app.models.conversation import Message

        result = await db.execute(
            select(Message).where(
                Message.provider_message_id == call_control_id
            )
        )
        message = result.scalar_one_or_none()

        if message:
            message.status = "completed"
            message.duration_seconds = duration_secs

            # Get recording URL if available
            recordings = payload.get("recordings", [])
            if recordings:
                # Typically Telnyx returns recording details here
                recording = recordings[0]
                message.recording_url = recording.get("public_url")
                log.info(
                    "recording_available",
                    recording_url=message.recording_url,
                )

            await db.commit()
            log.info("message_updated", message_id=str(message.id))


async def handle_machine_detection(payload: dict[Any, Any], log: Any) -> None:
    """Handle voicemail/machine detection result.

    Args:
        payload: Telnyx machine detection payload
        log: Logger instance
    """
    call_control_id = payload.get("call_control_id", "")
    result_type = payload.get("result", "")  # human, machine, silence

    log = log.bind(call_control_id=call_control_id, detection_result=result_type)
    log.info("machine_detection_result")

    # Can be used to handle voicemail differently or log analytics


async def auto_answer_call_if_agent_assigned(
    call_control_id: str,
    phone_record: PhoneNumber,
    conversation: Any,
    log: Any,
) -> None:
    """Auto-answer incoming call if an active agent is assigned to the phone number.

    This function:
    1. Checks if the phone number has an assigned agent
    2. Verifies the agent is active and supports voice
    3. Answers the call via Telnyx API
    4. Starts audio streaming to the voice bridge WebSocket

    Args:
        call_control_id: Telnyx call control ID
        phone_record: PhoneNumber database record
        conversation: Conversation database record
        log: Logger instance
    """
    from app.models.agent import Agent
    from app.services.telephony.telnyx_voice import TelnyxVoiceService

    if not settings.telnyx_api_key:
        log.warning("no_telnyx_api_key_for_auto_answer")
        return

    # Check if phone number has an assigned agent
    if not phone_record.assigned_agent_id:
        log.info("no_agent_assigned_to_phone_number", phone_number=phone_record.phone_number)
        return

    async with AsyncSessionLocal() as db:
        # Look up the agent
        result = await db.execute(
            select(Agent).where(Agent.id == phone_record.assigned_agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            log.warning(
                "assigned_agent_not_found",
                agent_id=str(phone_record.assigned_agent_id),
            )
            return

        # Check if agent is active and supports voice
        if not agent.is_active:
            log.info("agent_not_active", agent_id=str(agent.id))
            return

        if agent.channel_mode not in ("voice", "both"):
            log.info(
                "agent_does_not_support_voice",
                agent_id=str(agent.id),
                channel_mode=agent.channel_mode,
            )
            return

        log.info(
            "auto_answering_call_with_agent",
            agent_id=str(agent.id),
            agent_name=agent.name,
            call_control_id=call_control_id,
        )

        # Update conversation with assigned agent
        from app.models.conversation import Conversation

        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation.id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.assigned_agent_id = agent.id
            conv.ai_enabled = True
            await db.commit()

        # Answer the call via Telnyx
        voice_service = TelnyxVoiceService(settings.telnyx_api_key)
        try:
            answered = await voice_service.answer_call(call_control_id)

            if not answered:
                log.error("failed_to_answer_call", call_control_id=call_control_id)
                return

            log.info("call_answered_successfully", call_control_id=call_control_id)

            # Start audio streaming to the voice bridge WebSocket
            # The stream URL should point to our WebSocket endpoint
            api_base = settings.api_base_url or "https://example.com"
            # Convert https to wss for WebSocket
            ws_base = api_base.replace("https://", "wss://").replace("http://", "ws://")
            stream_url = f"{ws_base}/ws/voice/stream/{call_control_id}"

            streaming_started = await voice_service.start_streaming(
                call_control_id=call_control_id,
                stream_url=stream_url,
                stream_track="both",  # Stream both inbound and outbound audio
            )

            if streaming_started:
                log.info(
                    "audio_streaming_started",
                    call_control_id=call_control_id,
                    stream_url=stream_url,
                )
            else:
                log.error(
                    "failed_to_start_audio_streaming",
                    call_control_id=call_control_id,
                )

        finally:
            await voice_service.close()
