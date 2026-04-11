"""Telnyx SMS/MMS webhook handlers."""

from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.phone_number import PhoneNumber
from app.services.ai.text_agent import schedule_ai_response
from app.services.approval.command_processor_service import command_processor_service
from app.services.campaigns.conversation_syncer import CampaignConversationSyncer
from app.services.push_notifications import push_notification_service
from app.services.telephony.telnyx import TelnyxSMSService

_conversation_syncer = CampaignConversationSyncer()


async def handle_inbound_message(payload: dict[str, Any], log: Any) -> None:  # noqa: PLR0912, PLR0915
    """Handle inbound SMS message."""
    from app.utils.phone import normalize_phone_safe

    # Extract message details
    from_number = payload.get("from", {}).get("phone_number", "")
    to_list = payload.get("to", [])
    to_number = to_list[0].get("phone_number", "") if to_list else ""
    body = payload.get("text", "")
    message_id = payload.get("id", "")

    # Normalize phone numbers to E.164 format for consistent lookups
    from_number = normalize_phone_safe(from_number) or from_number
    to_number = normalize_phone_safe(to_number) or to_number

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

        # Check if this is an approval command (Y/N/approve/reject)
        is_command = await command_processor_service.try_process_command(
            db=db, from_number=from_number, to_number=to_number, body=body,
        )
        if is_command:
            log.info("processed_approval_command", from_number=from_number)
            return

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

            # Pause any active drip enrollments for this contact
            if message.conversation_id:
                try:
                    from app.models.conversation import Conversation as Conv
                    from app.services.reactivation.drip_runner import handle_inbound_reply

                    conv_for_drip = await db.execute(
                        select(Conv).where(
                            Conv.id == message.conversation_id
                        )
                    )
                    drip_conv = conv_for_drip.scalar_one_or_none()
                    if drip_conv and drip_conv.contact_id:
                        await handle_inbound_reply(
                            contact_id=drip_conv.contact_id,
                            workspace_id=workspace_id,
                            db=db,
                        )
                except Exception as e:
                    log.exception("drip_pause_on_reply_failed", error=str(e))

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
