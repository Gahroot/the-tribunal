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
from app.models.phone_number import PhoneNumber
from app.services.ai.text_agent import schedule_ai_response
from app.services.campaigns.conversation_syncer import CampaignConversationSyncer
from app.services.telephony.call_outcome_classifier import CallOutcomeClassifier
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.push_notifications import push_notification_service
from app.services.telephony.voice_agent_resolver import VoiceAgentResolver

router = APIRouter()
logger = structlog.get_logger()

# Shared service instances
_conversation_syncer = CampaignConversationSyncer()
_call_classifier = CallOutcomeClassifier()
_voice_agent_resolver = VoiceAgentResolver()


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
    """Handle inbound SMS message."""
    from app.services.telephony.telnyx import normalize_phone_number

    # Extract message details
    from_number = payload.get("from", {}).get("phone_number", "")
    to_list = payload.get("to", [])
    to_number = to_list[0].get("phone_number", "") if to_list else ""
    body = payload.get("text", "")
    message_id = payload.get("id", "")

    # Normalize phone numbers to E.164 format for consistent lookups
    from_number = normalize_phone_number(from_number)
    to_number = normalize_phone_number(to_number)

    log = log.bind(from_number=from_number, to_number=to_number, message_id=message_id)
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
                from app.models.conversation import Conversation

                conv_result = await db.execute(
                    select(Conversation).where(Conversation.id == message.conversation_id)
                )
                conversation = conv_result.scalar_one_or_none()

                if conversation:
                    # Sync campaign agent and AI settings
                    await _conversation_syncer.sync_conversation(db, conversation, log)

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

            # Update campaign reply stats
            if message.conversation_id:
                try:
                    from app.services.campaigns.campaign_sms_stats import update_campaign_sms_reply

                    await update_campaign_sms_reply(
                        db=db, conversation_id=message.conversation_id, log=log,
                    )
                except Exception as e:
                    log.exception("campaign_reply_stats_failed", error=str(e))

            log.info("inbound_sms_processed", message_id=str(message.id))

            # Push notification for inbound SMS
            try:
                truncated_body = body[:100] + "..." if len(body) > 100 else body
                await push_notification_service.send_to_workspace_members(
                    db=db,
                    workspace_id=str(workspace_id),
                    title="New Message",
                    body=truncated_body,
                    data={
                        "type": "message",
                        "conversationId": str(message.conversation_id),
                        "screen": f"/(tabs)/messages/{message.conversation_id}",
                    },
                    notification_type="message",
                    channel_id="messages",
                )
            except Exception as e:
                log.exception("push_notification_failed", error=str(e))
        finally:
            await sms_service.close()


async def handle_delivery_status(payload: dict[str, Any], log: Any) -> None:
    """Handle delivery status update with bounce classification."""
    message_id = payload.get("id", "")
    to_info = payload.get("to", [{}])[0] if payload.get("to") else {}
    status = to_info.get("status", "unknown")

    # Extract error details for bounce classification
    errors = payload.get("errors", [])
    first_error = errors[0] if errors else {}
    error_code = first_error.get("code") if first_error else None
    error_message = first_error.get("detail") if first_error else None

    log = log.bind(message_id=message_id, status=status, error_code=error_code)
    log.info("processing_delivery_status")

    async with AsyncSessionLocal() as db:
        telnyx_api_key = settings.telnyx_api_key
        if not telnyx_api_key:
            log.error("no_telnyx_api_key")
            return

        sms_service = TelnyxSMSService(telnyx_api_key)
        try:
            # Update message status with bounce classification
            message = await sms_service.update_message_status(
                db=db,
                provider_message_id=message_id,
                status=status,
                error_code=error_code,
                error_message=error_message,
            )

            # Track delivery stats if we have a phone number ID
            if message and message.from_phone_number_id:
                from app.services.rate_limiting.bounce_classifier import BounceClassifier
                from app.services.rate_limiting.reputation_tracker import ReputationTracker

                tracker = ReputationTracker()

                if message.status == "delivered":
                    await tracker.increment_delivered(message.from_phone_number_id, db)
                    log.info("delivery_tracked", phone_number_id=str(message.from_phone_number_id))

                elif message.status == "failed" and error_code:
                    # Classify the bounce
                    bounce_type, bounce_category = BounceClassifier.classify_error(
                        error_code, error_message
                    )

                    # Update message with bounce classification
                    message.bounce_type = bounce_type
                    message.bounce_category = bounce_category
                    message.carrier_error_code = error_code
                    await db.commit()

                    # Track appropriate counter
                    if bounce_type == "hard":
                        await tracker.increment_hard_bounce(message.from_phone_number_id, db)
                    elif bounce_type == "soft":
                        await tracker.increment_soft_bounce(message.from_phone_number_id, db)
                    elif bounce_type == "spam_complaint":
                        await tracker.increment_spam_complaint(message.from_phone_number_id, db)

                    log.info(
                        "bounce_tracked",
                        phone_number_id=str(message.from_phone_number_id),
                        bounce_type=bounce_type,
                        bounce_category=bounce_category,
                    )

            # Update campaign delivery stats (only for final statuses)
            if message and message.conversation_id and message.status in ("delivered", "failed"):
                try:
                    from app.services.campaigns.campaign_sms_stats import (
                        update_campaign_sms_delivery,
                    )

                    await update_campaign_sms_delivery(
                        db=db,
                        conversation_id=message.conversation_id,
                        delivered=(message.status == "delivered"),
                        log=log,
                    )
                except Exception as e:
                    log.exception("campaign_delivery_stats_failed", error=str(e))

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
    log.info(
        "========== TELNYX VOICE WEBHOOK ==========",
        event_type=event_type,
        call_control_id=event_payload.get("call_control_id"),
        call_state=event_payload.get("state"),
        direction=event_payload.get("direction"),
    )

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
        log.info("unhandled_voice_event_type", event_type=event_type)

    return {"status": "ok"}


def _extract_phone_numbers(payload: dict[Any, Any]) -> tuple[str, str]:
    """Extract and normalize phone numbers from Telnyx payload."""
    from app.services.telephony.telnyx import normalize_phone_number

    # Telnyx voice webhooks send "from" and "to" as strings or nested objects
    from_raw = payload.get("from", "")
    if isinstance(from_raw, dict):
        from_number = from_raw.get("phone_number", "")
    else:
        from_number = str(from_raw) if from_raw else ""

    to_raw = payload.get("to", "")
    if isinstance(to_raw, list):
        to_number = to_raw[0].get("phone_number", "") if len(to_raw) > 0 else ""
    elif isinstance(to_raw, dict):
        to_number = to_raw.get("phone_number", "")
    else:
        to_number = str(to_raw) if to_raw else ""

    return normalize_phone_number(from_number), normalize_phone_number(to_number)


async def handle_call_initiated(payload: dict[Any, Any], log: Any) -> None:
    """Handle incoming call."""
    call_control_id = payload.get("call_control_id", "")
    call_state = payload.get("state", "")
    from_number, to_number = _extract_phone_numbers(payload)

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
        from app.models.conversation import Conversation, Message

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
        message = Message(
            conversation_id=conversation.id,
            provider_message_id=call_control_id,
            direction="inbound",
            channel="voice",
            body="",
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

        # Push notification for incoming call
        try:
            await push_notification_service.send_to_workspace_members(
                db=db,
                workspace_id=str(workspace_id),
                title="Incoming Call",
                body=from_number,
                data={
                    "type": "call",
                    "messageId": str(message.id),
                    "screen": f"/call/{message.id}",
                },
                notification_type="call",
                channel_id="calls",
            )
        except Exception as e:
            log.exception("push_notification_failed", error=str(e))

        # Auto-answer calls if phone number has an assigned active agent
        await auto_answer_call_if_agent_assigned(
            call_control_id=call_control_id,
            phone_record=phone_record,
            conversation=conversation,
            log=log,
        )


async def handle_call_answered(payload: dict[Any, Any], log: Any) -> None:  # noqa: PLR0912, PLR0915
    """Handle call answered event."""
    from app.models.agent import Agent
    from app.models.conversation import Conversation, Message
    from app.services.telephony.telnyx_voice import TelnyxVoiceService

    call_control_id = payload.get("call_control_id", "")
    call_state = payload.get("state", "")
    direction = payload.get("direction", "")

    log = log.bind(call_control_id=call_control_id, call_state=call_state, direction=direction)
    log.info("========== CALL ANSWERED ==========")

    async with AsyncSessionLocal() as db:
        # Get message with conversation loaded
        result = await db.execute(
            select(Message)
            .options(selectinload(Message.conversation))
            .where(Message.provider_message_id == call_control_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            log.error("message_not_found_for_call", call_control_id=call_control_id)
            return

        message.status = "answered"
        await db.commit()

        # Determine agent_id: prefer message.agent_id, fall back to conversation's assigned_agent_id
        agent_id = message.agent_id
        if not agent_id and message.conversation and message.conversation.assigned_agent_id:
            agent_id = message.conversation.assigned_agent_id

        # For outbound calls with an agent, start audio streaming
        if message.direction == "outbound" and agent_id:
            log.info("outbound_call_answered_starting_stream", agent_id=str(agent_id))

            # Get agent to check if it supports voice
            agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = agent_result.scalar_one_or_none()

            if not agent or not agent.is_active:
                agent_str = str(agent_id) if agent_id else None
                log.info("agent_not_found_or_inactive", agent_id=agent_str)
                return

            # Assign agent to conversation if not already assigned
            if message.conversation and not message.conversation.assigned_agent_id:
                conv_result = await db.execute(
                    select(Conversation).where(Conversation.id == message.conversation_id)
                )
                conv = conv_result.scalar_one_or_none()
                if conv:
                    conv.assigned_agent_id = agent.id
                    conv.ai_enabled = True
                    await db.commit()
                    log.info("assigned_agent_to_conversation", agent_id=str(agent.id))

            # Start audio streaming
            if not settings.telnyx_api_key:
                log.error("no_telnyx_api_key_for_streaming")
                return

            voice_service = TelnyxVoiceService(settings.telnyx_api_key)
            try:
                api_base = settings.api_base_url or "https://example.com"
                streaming_started = await voice_service.start_audio_streaming(
                    call_control_id=call_control_id,
                    api_base_url=api_base,
                    is_outbound=True,
                )

                if streaming_started:
                    log.info("audio_streaming_started", call_control_id=call_control_id)
                else:
                    log.error("failed_to_start_audio_streaming", call_control_id=call_control_id)

                # Start recording if agent has it enabled
                if agent.enable_recording:
                    recorded = await voice_service.start_recording(call_control_id)
                    if recorded:
                        log.info("call_recording_started", call_control_id=call_control_id)
                    else:
                        log.warning("call_recording_failed", call_control_id=call_control_id)
            finally:
                await voice_service.close()


async def _reconcile_booking_outcome(
    db: Any, message: Any, log: Any,
) -> str | None:
    """Check for booking evidence when message.booking_outcome is NULL.

    Strategies:
    1. Query Appointment by message_id (direct link from VoiceToolExecutor).
    2. Query Appointment by contact_id + agent_id created within last 5 minutes.

    Returns the reconciled booking_outcome or None.
    """
    if message.booking_outcome:
        outcome: str = message.booking_outcome
        return outcome

    from datetime import timedelta

    from app.models.appointment import Appointment

    # Strategy 1: Direct message_id link
    appt_result = await db.execute(
        select(Appointment).where(Appointment.message_id == message.id)
    )
    appt = appt_result.scalar_one_or_none()
    if appt:
        log.info("reconciled_booking_via_message_id", appointment_id=appt.id)
        return "success"

    # Strategy 2: Fuzzy match by contact + agent + recent creation
    if message.conversation and message.conversation.contact_id and message.agent_id:
        cutoff = datetime.now(UTC) - timedelta(minutes=5)
        fuzzy_result = await db.execute(
            select(Appointment).where(
                Appointment.contact_id == message.conversation.contact_id,
                Appointment.agent_id == message.agent_id,
                Appointment.created_at >= cutoff,
            )
        )
        fuzzy_appt = fuzzy_result.scalar_one_or_none()
        if fuzzy_appt:
            # Backfill the message_id link
            fuzzy_appt.message_id = message.id
            log.info(
                "reconciled_booking_via_fuzzy_match",
                appointment_id=fuzzy_appt.id,
            )
            return "success"

    return None


async def handle_call_hangup(payload: dict[Any, Any], log: Any) -> None:  # noqa: PLR0912, PLR0915
    """Handle call hangup event."""
    call_control_id = payload.get("call_control_id", "")
    duration_secs = payload.get("duration_seconds", 0)
    hangup_cause = payload.get("hangup_cause", "")
    hangup_source = payload.get("hangup_source", "")

    log = log.bind(
        call_control_id=call_control_id,
        duration=duration_secs,
        hangup_cause=hangup_cause,
        hangup_source=hangup_source,
    )
    log.info("call_hangup")

    async with AsyncSessionLocal() as db:
        from app.models.conversation import Message

        result = await db.execute(
            select(Message)
            .options(selectinload(Message.conversation))
            .where(Message.provider_message_id == call_control_id)
        )
        message = result.scalar_one_or_none()

        if message:
            # Reconcile booking outcome before classification
            reconciled = await _reconcile_booking_outcome(db, message, log)
            if reconciled and not message.booking_outcome:
                message.booking_outcome = reconciled
            # Use stored streaming duration if hangup reports 0
            # (Telnyx doesn't populate duration_seconds for streaming/WebSocket calls)
            if duration_secs > 0:
                message.duration_seconds = duration_secs
            elif message.duration_seconds and message.duration_seconds > 0:
                duration_secs = message.duration_seconds
            else:
                message.duration_seconds = duration_secs

            # Get recording URL if available
            recordings = payload.get("recordings", [])
            if recordings:
                message.recording_url = recordings[0].get("public_url")
                log.info("recording_available", recording_url=message.recording_url)

            # Classify the call outcome
            classification = _call_classifier.classify(
                hangup_cause=hangup_cause,
                duration_secs=duration_secs,
                hangup_source=hangup_source,
                booking_outcome=message.booking_outcome,
            )

            message.status = classification.message_status

            # Store error info for failed calls
            if classification.error_code:
                message.error_code = classification.error_code
                message.error_message = classification.error_message

            if classification.is_rejection:
                log.info("rejected_call_detected", hangup_source=hangup_source)

            # Override if booking was successful
            if message.booking_outcome == "success" and classification.message_status == "failed":
                log.info("overriding_failed_status_due_to_successful_booking")
                message.status = "completed"

            await db.commit()
            log.info("message_updated", message_id=str(message.id), status=message.status)

            # Push notification for missed/failed inbound calls
            if message.direction == "inbound" and message.status in ("no_answer", "failed"):
                try:
                    from_number, _ = _extract_phone_numbers(payload)
                    workspace_id = (
                        message.conversation.workspace_id if message.conversation else None
                    )
                    if workspace_id:
                        await push_notification_service.send_to_workspace_members(
                            db=db,
                            workspace_id=str(workspace_id),
                            title="Missed Call",
                            body=from_number,
                            data={
                                "type": "missed_call",
                                "messageId": str(message.id),
                                "screen": f"/(tabs)/calls/{message.id}",
                            },
                            notification_type="call",
                            channel_id="calls",
                        )
                except Exception as e:
                    log.exception("push_notification_failed", error=str(e))

            # Create CallOutcome record for attribution and analysis
            try:
                from app.services.ai.call_outcome_service import create_outcome_from_hangup

                await create_outcome_from_hangup(
                    db=db,
                    message_id=message.id,
                    hangup_cause=hangup_cause,
                    duration_secs=duration_secs,
                    booking_outcome=message.booking_outcome,
                )
                log.info("call_outcome_created", message_id=str(message.id))
            except Exception as e:
                log.exception("call_outcome_creation_failed", error=str(e))

            # Update campaign stats for ALL calls (successful and failed)
            try:
                from app.services.campaigns.campaign_call_stats import (
                    update_campaign_call_stats,
                )

                await update_campaign_call_stats(
                    db=db,
                    message_id=message.id,
                    call_outcome=classification.outcome,
                    message_status=classification.message_status,
                    duration_secs=duration_secs,
                    log=log,
                    booking_outcome=message.booking_outcome,
                )
            except Exception as e:
                log.exception("campaign_call_stats_update_failed", error=str(e))

            # Trigger SMS fallback for failed calls only
            if classification.outcome:
                log.info("triggering_sms_fallback", call_outcome=classification.outcome)
                try:
                    from app.services.campaigns.sms_fallback import trigger_sms_fallback_for_call

                    await trigger_sms_fallback_for_call(
                        call_control_id=call_control_id,
                        call_outcome=classification.outcome,
                        log=log,
                    )
                except Exception as e:
                    log.exception("sms_fallback_trigger_failed", error=str(e))


async def handle_machine_detection(payload: dict[Any, Any], log: Any) -> None:
    """Handle voicemail/machine detection result."""
    call_control_id = payload.get("call_control_id", "")
    result_type = payload.get("result", "")

    log = log.bind(call_control_id=call_control_id, detection_result=result_type)
    log.info("machine_detection_result")

    # Check if voicemail/machine detected
    call_outcome = _call_classifier.classify_machine_detection(result_type)
    if not call_outcome:
        return

    log.info("voicemail_detected_hanging_up")

    # Push notification for voicemail
    try:
        from app.models.conversation import Message

        async with AsyncSessionLocal() as push_db:
            msg_result = await push_db.execute(
                select(Message)
                .options(selectinload(Message.conversation))
                .where(Message.provider_message_id == call_control_id)
            )
            msg = msg_result.scalar_one_or_none()
            if msg and msg.conversation:
                from_number, _ = _extract_phone_numbers(payload)
                await push_notification_service.send_to_workspace_members(
                    db=push_db,
                    workspace_id=str(msg.conversation.workspace_id),
                    title="New Voicemail",
                    body=from_number,
                    data={
                        "type": "voicemail",
                        "messageId": str(msg.id),
                        "screen": f"/(tabs)/calls/{msg.id}",
                    },
                    notification_type="voicemail",
                    channel_id="calls",
                )
    except Exception as e:
        log.exception("push_notification_failed", error=str(e))

    # Hang up the call
    from app.services.telephony.telnyx_voice import TelnyxVoiceService

    if settings.telnyx_api_key:
        voice_service = TelnyxVoiceService(settings.telnyx_api_key)
        try:
            await voice_service.hangup_call(call_control_id)
            log.info("call_hung_up_on_voicemail")
        except Exception as e:
            log.exception("hangup_failed", error=str(e))
        finally:
            await voice_service.close()

        # Trigger SMS fallback
        try:
            from app.services.campaigns.sms_fallback import trigger_sms_fallback_for_call

            await trigger_sms_fallback_for_call(
                call_control_id=call_control_id,
                call_outcome=call_outcome,
                log=log,
            )
        except Exception as e:
            log.exception("sms_fallback_trigger_failed", error=str(e))


async def auto_answer_call_if_agent_assigned(
    call_control_id: str,
    phone_record: PhoneNumber,
    conversation: Any,
    log: Any,
) -> None:
    """Auto-answer incoming call if an active agent is assigned."""
    from app.models.conversation import Conversation
    from app.services.telephony.telnyx_voice import TelnyxVoiceService

    log.info(
        "========== AUTO ANSWER CHECK ==========",
        call_control_id=call_control_id,
        phone_number=phone_record.phone_number,
        phone_assigned_agent_id=str(phone_record.assigned_agent_id)
        if phone_record.assigned_agent_id
        else None,
        conversation_id=str(conversation.id) if conversation else None,
    )

    if not settings.telnyx_api_key:
        log.warning("no_telnyx_api_key_for_auto_answer")
        return

    async with AsyncSessionLocal() as db:
        resolved = await _voice_agent_resolver.resolve(db, conversation, phone_record, log)

        if not resolved:
            log.info(
                "no_valid_voice_agent_found",
                phone_number=phone_record.phone_number,
                hint="Assign a voice-capable agent to the phone number or campaign",
            )
            return

        log.info(
            "auto_answering_call_with_agent",
            agent_id=str(resolved.agent.id),
            agent_name=resolved.agent.name,
            agent_source=resolved.source,
            call_control_id=call_control_id,
        )

        # Update conversation with assigned agent
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation.id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.assigned_agent_id = resolved.agent.id
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

            # Start audio streaming
            api_base = settings.api_base_url or "https://example.com"
            streaming_started = await voice_service.start_audio_streaming(
                call_control_id=call_control_id,
                api_base_url=api_base,
                is_outbound=False,
            )

            if streaming_started:
                log.info("audio_streaming_started", call_control_id=call_control_id)
            else:
                log.error("failed_to_start_audio_streaming", call_control_id=call_control_id)

            # Start recording if agent has it enabled
            if resolved.agent.enable_recording:
                recorded = await voice_service.start_recording(call_control_id)
                if recorded:
                    log.info("call_recording_started", call_control_id=call_control_id)
                else:
                    log.warning("call_recording_failed", call_control_id=call_control_id)

        finally:
            await voice_service.close()
