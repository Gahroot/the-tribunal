"""Voice bridge WebSocket endpoint for Telnyx media streaming.

This module handles bidirectional audio streaming between Telnyx (telephony)
and AI voice providers (OpenAI/Grok). Key considerations:

- Telnyx uses μ-law (G.711) at 8kHz sample rate
- OpenAI/Grok Realtime API uses PCM16 at 24kHz
- Audio must be converted and resampled in both directions (3x ratio)
- Supports tool calling for Cal.com booking integration
"""

import asyncio
import audioop
import base64
import contextlib
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.ai.grok_voice_agent import GrokVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession
from app.services.calendar.calcom import CalComService

router = APIRouter()
logger = structlog.get_logger()

# Audio format constants
# Telnyx uses μ-law (G.711) at 8kHz, OpenAI/Grok uses PCM16 at 24kHz
TELNYX_SAMPLE_RATE = 8000  # 8kHz for PSTN/Telnyx (μ-law/G.711)
OPENAI_SAMPLE_RATE = 24000  # 24kHz for OpenAI/Grok Realtime API


def mulaw_to_pcm(data: bytes) -> bytes:
    """Convert μ-law audio to PCM16 using Python's audioop.

    Args:
        data: μ-law encoded audio bytes (8kHz)

    Returns:
        PCM16 audio bytes (little-endian, 8kHz)
    """
    # audioop.ulaw2lin converts μ-law to linear PCM
    # 2 = sample width in bytes (16-bit)
    return audioop.ulaw2lin(data, 2)


def pcm_to_mulaw(data: bytes) -> bytes:
    """Convert PCM16 audio to μ-law using Python's audioop.

    Args:
        data: PCM16 audio bytes (little-endian)

    Returns:
        μ-law encoded audio bytes
    """
    # audioop.lin2ulaw converts linear PCM to μ-law
    # 2 = sample width in bytes (16-bit)
    return audioop.lin2ulaw(data, 2)


def upsample_8k_to_24k(data: bytes) -> bytes:
    """Upsample PCM16 audio from 8kHz to 24kHz using audioop.ratecv.

    Args:
        data: PCM16 audio bytes at 8kHz

    Returns:
        PCM16 audio bytes at 24kHz (3x samples)
    """
    if len(data) < 2:
        return data

    # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
    # width=2 for 16-bit, nchannels=1 for mono
    # Returns (newfragment, newstate)
    result, _ = audioop.ratecv(data, 2, 1, TELNYX_SAMPLE_RATE, OPENAI_SAMPLE_RATE, None)
    return result


def downsample_24k_to_8k(data: bytes) -> bytes:
    """Downsample PCM16 audio from 24kHz to 8kHz using audioop.ratecv.

    Args:
        data: PCM16 audio bytes at 24kHz

    Returns:
        PCM16 audio bytes at 8kHz (1/3x samples)
    """
    if len(data) < 2:
        return data

    # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
    result, _ = audioop.ratecv(data, 2, 1, OPENAI_SAMPLE_RATE, TELNYX_SAMPLE_RATE, None)
    return result


def convert_telnyx_to_openai(mulaw_8k: bytes, log: Any) -> bytes:
    """Convert Telnyx μ-law 8kHz audio to OpenAI/Grok PCM16 24kHz.

    Pipeline: μ-law 8kHz → PCM16 8kHz → PCM16 24kHz

    Args:
        mulaw_8k: μ-law encoded audio at 8kHz from Telnyx
        log: Logger instance

    Returns:
        PCM16 audio at 24kHz for OpenAI/Grok Realtime API
    """
    # Step 1: μ-law to PCM16 (still at 8kHz)
    pcm_8k = mulaw_to_pcm(mulaw_8k)

    # Step 2: Upsample 8kHz to 24kHz (3x)
    pcm_24k = upsample_8k_to_24k(pcm_8k)

    return pcm_24k


def convert_openai_to_telnyx(pcm_24k: bytes, log: Any) -> bytes:
    """Convert OpenAI/Grok PCM16 24kHz audio to Telnyx μ-law 8kHz.

    Pipeline: PCM16 24kHz → PCM16 8kHz → μ-law 8kHz

    Args:
        pcm_24k: PCM16 audio at 24kHz from OpenAI/Grok Realtime API
        log: Logger instance

    Returns:
        μ-law encoded audio at 8kHz for Telnyx
    """
    # Step 1: Downsample 24kHz to 8kHz (3x)
    pcm_8k = downsample_24k_to_8k(pcm_24k)

    # Step 2: PCM16 to μ-law
    mulaw_8k = pcm_to_mulaw(pcm_8k)

    return mulaw_8k


async def _lookup_call_context(
    call_id: str,
    log: Any,
) -> tuple[Any, dict[str, Any] | None, dict[str, Any] | None, str]:
    """Look up agent, contact, and offer context for a call.

    Args:
        call_id: Telnyx call control ID (provider_message_id)
        log: Logger instance

    Returns:
        Tuple of (agent, contact_info dict, offer_info dict, timezone)
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.agent import Agent
    from app.models.campaign import CampaignContact
    from app.models.contact import Contact
    from app.models.conversation import Message
    from app.models.offer import Offer
    from app.models.workspace import Workspace

    agent = None
    contact_info = None
    offer_info = None
    timezone = "America/New_York"  # Default fallback

    async with AsyncSessionLocal() as db:
        # Look up the message record for this call
        msg_result = await db.execute(
            select(Message)
            .options(selectinload(Message.conversation))
            .where(Message.provider_message_id == call_id)
        )
        message = msg_result.scalar_one_or_none()

        if not message or not message.conversation:
            log.warning("message_not_found_for_call", call_id=call_id)
            return agent, contact_info, offer_info, timezone

        conversation = message.conversation

        # Get workspace timezone
        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == conversation.workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        if workspace and workspace.settings:
            timezone = workspace.settings.get("timezone", "America/New_York")

        # Look up the assigned agent
        if conversation.assigned_agent_id:
            agent_result = await db.execute(
                select(Agent).where(Agent.id == conversation.assigned_agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if agent:
                log.info(
                    "found_agent_for_call",
                    agent_id=str(agent.id),
                    agent_name=agent.name,
                )

        # Look up contact info
        if conversation.contact_id:
            contact_result = await db.execute(
                select(Contact).where(Contact.id == conversation.contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact:
                contact_info = {
                    "name": f"{contact.first_name} {contact.last_name or ''}".strip(),
                    "phone": contact.phone_number,
                    "email": contact.email,
                    "company": contact.company_name,
                    "status": contact.status,
                }
                log.info("found_contact_for_call", contact_id=contact.id)

        # Look up offer info from campaign if applicable
        campaign_contact_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.campaign))
            .where(CampaignContact.conversation_id == conversation.id)
        )
        campaign_contact = campaign_contact_result.scalar_one_or_none()

        if campaign_contact and campaign_contact.campaign:
            campaign = campaign_contact.campaign
            if campaign.offer_id:
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == campaign.offer_id)
                )
                offer = offer_result.scalar_one_or_none()
                if offer:
                    offer_info = {
                        "name": offer.name,
                        "description": offer.description,
                        "discount_type": offer.discount_type,
                        "discount_value": float(offer.discount_value),
                        "terms": offer.terms,
                    }
                    log.info(
                        "found_offer_for_call",
                        offer_id=str(offer.id),
                        offer_name=offer.name,
                    )

    return agent, contact_info, offer_info, timezone


async def _execute_voice_tool(
    call_id: str,
    function_name: str,
    arguments: dict[str, Any],
    agent: Any,
    contact_info: dict[str, Any] | None,
    timezone: str,
    log: Any,
) -> dict[str, Any]:
    """Execute a tool call from voice agent.

    Args:
        call_id: Function call ID from Grok
        function_name: Name of function to execute
        arguments: Function arguments
        agent: Agent model with Cal.com config
        contact_info: Contact information
        timezone: Timezone for bookings (from workspace settings)
        log: Logger instance

    Returns:
        Tool execution result
    """
    log.info(
        "executing_voice_tool",
        call_id=call_id,
        function_name=function_name,
        arguments=arguments,
    )

    if function_name == "check_availability":
        return await _execute_check_availability(
            agent=agent,
            start_date_str=arguments.get("start_date", ""),
            end_date_str=arguments.get("end_date"),
            timezone=timezone,
            log=log,
        )

    elif function_name == "book_appointment":
        return await _execute_book_appointment(
            agent=agent,
            contact_info=contact_info,
            date_str=arguments.get("date", ""),
            time_str=arguments.get("time", ""),
            email=arguments.get("email"),
            duration_minutes=arguments.get("duration_minutes", 30),
            notes=arguments.get("notes"),
            timezone=timezone,
            log=log,
        )

    else:
        log.warning("unknown_voice_tool", function_name=function_name)
        return {"success": False, "error": f"Unknown function: {function_name}"}


async def _execute_check_availability(
    agent: Any,
    start_date_str: str,
    end_date_str: str | None,
    timezone: str,
    log: Any,
) -> dict[str, Any]:
    """Execute check_availability tool.

    Args:
        agent: Agent with Cal.com event type ID
        start_date_str: Start date in YYYY-MM-DD format
        end_date_str: Optional end date
        timezone: Timezone for availability
        log: Logger instance

    Returns:
        Available slots or error
    """
    if not agent or not agent.calcom_event_type_id:
        return {"success": False, "error": "Cal.com not configured for this agent"}

    if not settings.calcom_api_key:
        return {"success": False, "error": "Cal.com API key not configured"}

    try:
        # Parse dates
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("America/New_York")

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=tz)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=tz)
        else:
            end_date = start_date

        # Get availability from Cal.com
        calcom_service = CalComService(settings.calcom_api_key)
        try:
            slots = await calcom_service.get_availability(
                event_type_id=agent.calcom_event_type_id,
                start_date=start_date,
                end_date=end_date,
                timezone=timezone,
            )

            log.info("availability_fetched", slot_count=len(slots))

            # Format slots for voice response
            if not slots:
                return {
                    "success": True,
                    "available": False,
                    "message": f"No available slots on {start_date_str}",
                }

            # Format slots nicely for voice
            slot_descriptions = []
            for slot in slots[:5]:  # Limit to 5 for voice
                slot_time = slot.get("time", "")
                slot_descriptions.append(slot_time)

            return {
                "success": True,
                "available": True,
                "slots": slots[:10],
                "message": f"Available times: {', '.join(slot_descriptions)}",
            }

        finally:
            await calcom_service.close()

    except Exception as e:
        log.exception("check_availability_error", error=str(e))
        return {"success": False, "error": f"Failed to check availability: {str(e)}"}


async def _execute_book_appointment(
    agent: Any,
    contact_info: dict[str, Any] | None,
    date_str: str,
    time_str: str,
    email: str | None,
    duration_minutes: int,
    notes: str | None,
    timezone: str,
    log: Any,
) -> dict[str, Any]:
    """Execute book_appointment tool.

    Args:
        agent: Agent with Cal.com event type ID
        contact_info: Contact information (name, phone)
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format
        email: Customer email address
        duration_minutes: Appointment duration
        notes: Optional notes
        timezone: Timezone for booking
        log: Logger instance

    Returns:
        Booking confirmation or error
    """
    if not agent or not agent.calcom_event_type_id:
        return {"success": False, "error": "Cal.com not configured for this agent"}

    if not settings.calcom_api_key:
        return {"success": False, "error": "Cal.com API key not configured"}

    if not email:
        return {
            "success": False,
            "error": "Email address is required for booking",
            "message": "Please ask the customer for their email address",
        }

    # Get contact name
    contact_name = "Customer"
    contact_phone = None
    if contact_info:
        contact_name = contact_info.get("name", "Customer")
        contact_phone = contact_info.get("phone")

    try:
        # Parse date and time
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("America/New_York")

        datetime_str = f"{date_str} {time_str}"
        start_time = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)

        # Convert to UTC for Cal.com
        start_utc = start_time.astimezone(ZoneInfo("UTC"))

        # Create booking via Cal.com
        calcom_service = CalComService(settings.calcom_api_key)
        try:
            booking = await calcom_service.create_booking(
                event_type_id=agent.calcom_event_type_id,
                contact_email=email,
                contact_name=contact_name,
                start_time=start_utc,
                duration_minutes=duration_minutes,
                metadata={"notes": notes} if notes else None,
                timezone=timezone,
                phone_number=contact_phone,
            )

            log.info(
                "booking_created",
                booking_uid=booking.get("data", {}).get("uid"),
                email=email,
            )

            return {
                "success": True,
                "booking_id": booking.get("data", {}).get("uid"),
                "message": (
                    f"Appointment booked for {contact_name} on {date_str} at {time_str}. "
                    f"Confirmation email sent to {email}."
                ),
            }

        finally:
            await calcom_service.close()

    except Exception as e:
        log.exception("book_appointment_error", error=str(e))
        return {"success": False, "error": f"Failed to book appointment: {str(e)}"}


def _create_voice_session(
    voice_provider: str,
    agent: Any,
) -> tuple[VoiceAgentSession | GrokVoiceAgentSession | None, str | None]:
    """Create appropriate voice session based on provider.

    Args:
        voice_provider: Provider name (openai, grok)
        agent: Agent model for configuration

    Returns:
        Tuple of (voice_session, error_message)
    """
    if voice_provider == "grok":
        if not settings.xai_api_key:
            return None, "xAI API key not configured"

        # Enable tools if agent has Cal.com configured
        enable_tools = bool(
            agent
            and agent.calcom_event_type_id
            and settings.calcom_api_key
        )

        return GrokVoiceAgentSession(
            settings.xai_api_key,
            agent,
            enable_tools=enable_tools,
        ), None

    # Default to OpenAI
    if not settings.openai_api_key:
        return None, "OpenAI API key not configured"
    return VoiceAgentSession(settings.openai_api_key, agent), None


async def _setup_voice_session(
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    agent: Any,
    contact_info: dict[str, Any] | None,
    offer_info: dict[str, Any] | None,
    timezone: str,
    log: Any,
) -> None:
    """Configure voice session with agent settings and context.

    Note: The greeting is NOT sent here. It's triggered when the Telnyx
    stream starts (in _receive_from_telnyx_and_send_to_provider) to ensure
    audio is ready before the AI starts speaking.

    Args:
        voice_session: Voice provider session
        agent: Agent model for configuration
        contact_info: Contact information dict
        offer_info: Offer information dict
        timezone: Timezone for bookings (from workspace settings)
        log: Logger instance
    """
    # Set up tool callback for Grok voice sessions
    if isinstance(voice_session, GrokVoiceAgentSession):
        # Create a closure to capture agent, contact_info, and timezone for tool execution
        async def tool_callback(
            call_id: str,
            function_name: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            return await _execute_voice_tool(
                call_id=call_id,
                function_name=function_name,
                arguments=arguments,
                agent=agent,
                contact_info=contact_info,
                timezone=timezone,
                log=log,
            )

        voice_session.set_tool_callback(tool_callback)
        log.info("tool_callback_configured")

    if agent:
        await voice_session.configure_session(
            voice=agent.voice_id,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            turn_detection_mode=agent.turn_detection_mode,
            turn_detection_threshold=agent.turn_detection_threshold,
            silence_duration_ms=agent.silence_duration_ms,
        )
        log.info("session_configured_with_agent_settings", agent_name=agent.name)

    if contact_info or offer_info:
        await voice_session.inject_context(
            contact_info=contact_info,
            offer_info=offer_info,
        )
        log.info("context_injected", has_contact=bool(contact_info), has_offer=bool(offer_info))

    # Note: Greeting is triggered when Telnyx stream starts, not here
    if agent and agent.initial_greeting:
        log.info("initial_greeting_prepared", greeting_length=len(agent.initial_greeting))


@router.websocket("/voice/stream/{call_id}")
async def voice_stream_bridge(websocket: WebSocket, call_id: str) -> None:  # noqa: PLR0915
    """Bridge between Telnyx media stream and voice AI provider.

    This WebSocket endpoint receives audio from Telnyx (μ-law 8kHz) and
    relays it to OpenAI/Grok (PCM16 24kHz), and vice versa.

    Supports multiple providers:
    - OpenAI Realtime API (default)
    - Grok (xAI) Realtime API

    Args:
        websocket: WebSocket connection from Telnyx
        call_id: Telnyx call control ID
    """
    connection_start = time.time()
    log = logger.bind(endpoint="voice_stream_bridge", call_id=call_id)
    log.info(
        "voice_bridge_connection_received",
        client_host=websocket.client.host if websocket.client else "unknown",
    )

    await websocket.accept()
    log.info("websocket_accepted")

    # Get agent and conversation context from database first to determine provider
    log.info("looking_up_call_context")
    agent, contact_info, offer_info, timezone = await _lookup_call_context(call_id, log)

    if not agent:
        log.warning(
            "no_agent_found_for_call",
            call_id=call_id,
            hint="Check that call has associated message with agent_id",
        )

    # Determine which voice provider to use
    voice_provider = "openai"  # default
    if agent and agent.voice_provider:
        voice_provider = agent.voice_provider.lower()

    log.info(
        "voice_provider_selected",
        provider=voice_provider,
        agent_name=agent.name if agent else None,
        agent_id=str(agent.id) if agent else None,
        has_contact=contact_info is not None,
        has_offer=offer_info is not None,
    )

    # Create appropriate voice session based on provider
    voice_session, error = _create_voice_session(voice_provider, agent)
    if voice_session is None:
        log.error(
            "api_key_not_configured",
            provider=voice_provider,
            error=error,
        )
        await websocket.send_json({"error": error})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    relay_task: asyncio.Task[None] | None = None

    try:
        # Connect to voice provider
        log.info("connecting_to_voice_provider", provider=voice_provider)
        connect_start = time.time()

        if not await voice_session.connect():
            connect_elapsed = time.time() - connect_start
            log.error(
                "failed_to_connect_to_voice_provider",
                provider=voice_provider,
                elapsed_secs=round(connect_elapsed, 2),
            )
            await websocket.send_json(
                {"error": f"Failed to connect to {voice_provider} Realtime API"}
            )
            await websocket.close(code=status.WS_1011_SERVER_ERROR)
            return

        connect_elapsed = time.time() - connect_start
        log.info(
            "connected_to_voice_provider",
            provider=voice_provider,
            connect_time_secs=round(connect_elapsed, 2),
        )

        # Configure session with agent settings and inject context
        log.info("configuring_voice_session")
        await _setup_voice_session(voice_session, agent, contact_info, offer_info, timezone, log)
        log.info("voice_session_configured")

        # Start bidirectional audio relay
        log.info("starting_relay_task")
        relay_task = asyncio.create_task(
            _relay_audio(websocket, voice_session, log)
        )

        # Wait for relay to complete (it will run until disconnect)
        await relay_task
        log.info("relay_task_completed")

    except WebSocketDisconnect:
        elapsed = time.time() - connection_start
        log.info(
            "telnyx_websocket_disconnected",
            total_connection_secs=round(elapsed, 1),
        )
    except asyncio.CancelledError:
        log.info("voice_bridge_cancelled")
    except Exception as e:
        elapsed = time.time() - connection_start
        log.exception(
            "voice_bridge_error",
            error=str(e),
            total_connection_secs=round(elapsed, 1),
        )
    finally:
        # Clean up
        if relay_task and not relay_task.done():
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task

        log.info("disconnecting_from_voice_provider")
        await voice_session.disconnect()

        with contextlib.suppress(Exception):
            await websocket.close()

        elapsed = time.time() - connection_start
        log.info(
            "voice_bridge_session_ended",
            total_duration_secs=round(elapsed, 1),
        )


async def _relay_audio(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
) -> None:
    """Relay audio bidirectionally between Telnyx and voice provider.

    This function manages two concurrent tasks:
    1. Receiving audio from Telnyx and sending to OpenAI/Grok
    2. Receiving audio from OpenAI/Grok and sending to Telnyx

    A synchronization event ensures audio is only sent to Telnyx after
    the greeting has been triggered and the stream is ready.

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: Voice provider session (OpenAI or Grok)
        log: Logger instance
    """
    # Event to synchronize greeting trigger with audio sending
    greeting_triggered = asyncio.Event()

    log.info("starting_audio_relay")

    # Create tasks for bidirectional streaming
    send_task = asyncio.create_task(
        _receive_from_telnyx_and_send_to_provider(
            websocket, voice_session, log, greeting_triggered
        )
    )
    recv_task = asyncio.create_task(
        _receive_from_provider_and_send_to_telnyx(
            websocket, voice_session, log, greeting_triggered
        )
    )

    try:
        # Wait for either task to complete or fail
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Log which task completed
        for task in done:
            if task == send_task:
                log.info("telnyx_receive_task_completed")
            else:
                log.info("provider_receive_task_completed")

        # Cancel remaining tasks gracefully
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Check for exceptions in completed tasks
        for task in done:
            exc = task.exception()
            if exc:
                log.error(
                    "relay_task_failed",
                    task="telnyx_receive" if task == send_task else "provider_receive",
                    error=str(exc),
                )

    except asyncio.CancelledError:
        log.info("relay_cancelled")
        # Cancel both tasks
        send_task.cancel()
        recv_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(send_task, recv_task)
    except Exception as e:
        log.exception("relay_error", error=str(e))


async def _receive_from_telnyx_and_send_to_provider(  # noqa: PLR0912, PLR0915
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
    greeting_triggered: asyncio.Event,
) -> None:
    """Receive audio from Telnyx and send to voice provider.

    Telnyx sends JSON messages with the following format:
    - {"event": "start", "stream_id": "...", "start": {"call_control_id": "..."}}
    - {"event": "media", "media": {"payload": "<base64-audio>"}}
    - {"event": "stop"}

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: Voice provider session (OpenAI or Grok)
        log: Logger instance
        greeting_triggered: Event to signal when greeting has been triggered
    """
    import json

    stream_started = False
    audio_chunks_received = 0
    total_audio_bytes = 0
    start_time = time.time()

    try:
        while True:
            # Receive JSON message from Telnyx
            raw_data = await websocket.receive_text()

            try:
                data = json.loads(raw_data)
                event = data.get("event", "")

                if event == "start":
                    # Stream has started - Telnyx is ready to send/receive audio
                    stream_id = data.get("stream_id", "")
                    start_info = data.get("start", {})
                    call_control_id = start_info.get("call_control_id", "")
                    media_format = start_info.get("media_format", {})
                    stream_started = True

                    log.info(
                        "telnyx_stream_started",
                        stream_id=stream_id,
                        call_control_id=call_control_id,
                        encoding=media_format.get("encoding", "unknown"),
                        sample_rate=media_format.get("sample_rate", "unknown"),
                        channels=media_format.get("channels", "unknown"),
                    )

                    # Trigger initial greeting - no artificial delay needed
                    # The stream is ready when we receive the "start" event
                    log.info("triggering_initial_greeting")
                    await voice_session.trigger_initial_response()
                    greeting_triggered.set()
                    log.info("initial_greeting_triggered")

                elif event == "media" and stream_started:
                    # Audio data received from caller
                    media = data.get("media", {})
                    payload = media.get("payload", "")
                    timestamp = media.get("timestamp", "")
                    chunk_num = media.get("chunk", "")

                    if payload:
                        # Decode base64 μ-law audio (8kHz)
                        audio_mulaw = base64.b64decode(payload)
                        audio_chunks_received += 1
                        total_audio_bytes += len(audio_mulaw)

                        # Convert μ-law 8kHz to PCM16 24kHz for OpenAI/Grok
                        audio_pcm = convert_telnyx_to_openai(audio_mulaw, log)

                        # Send to voice provider
                        await voice_session.send_audio_chunk(audio_pcm)

                        # Log periodically (every 50 chunks = ~1 second of audio)
                        if audio_chunks_received % 50 == 0:
                            elapsed = time.time() - start_time
                            log.debug(
                                "audio_relay_stats",
                                direction="telnyx_to_provider",
                                chunks=audio_chunks_received,
                                total_bytes=total_audio_bytes,
                                elapsed_secs=round(elapsed, 1),
                                timestamp=timestamp,
                                chunk=chunk_num,
                            )

                elif event == "stop":
                    elapsed = time.time() - start_time
                    log.info(
                        "telnyx_stream_stopped",
                        total_chunks=audio_chunks_received,
                        total_bytes=total_audio_bytes,
                        duration_secs=round(elapsed, 1),
                    )
                    break

                elif event == "error":
                    error_msg = data.get("error", {}).get("message", "unknown")
                    log.error("telnyx_stream_error", error=error_msg)
                    break

                else:
                    log.debug("telnyx_unknown_event", telnyx_event=event)

            except json.JSONDecodeError as e:
                log.warning(
                    "telnyx_invalid_json",
                    error=str(e),
                    raw_data_preview=raw_data[:100] if raw_data else "empty",
                )
            except Exception as e:
                log.exception(
                    "telnyx_audio_processing_error",
                    error=str(e),
                    event=data.get("event", "unknown") if "data" in dir() else "unknown",
                )

    except WebSocketDisconnect:
        elapsed = time.time() - start_time
        log.info(
            "telnyx_websocket_disconnected",
            total_chunks=audio_chunks_received,
            duration_secs=round(elapsed, 1),
        )
    except asyncio.CancelledError:
        log.info("telnyx_receive_cancelled")
        raise
    except Exception as e:
        log.exception("receive_from_telnyx_error", error=str(e))


async def _receive_from_provider_and_send_to_telnyx(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
    greeting_triggered: asyncio.Event,
) -> None:
    """Receive audio from voice provider and send to Telnyx.

    Sends audio in Telnyx's expected JSON format:
    {"event": "media", "media": {"payload": "<base64-audio>"}}

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: Voice provider session (OpenAI or Grok)
        log: Logger instance
        greeting_triggered: Event to wait for before sending audio
    """
    import json

    audio_chunks_sent = 0
    total_audio_bytes = 0
    start_time = time.time()
    first_audio_time: float | None = None

    try:
        # Wait for greeting to be triggered before sending audio
        # This ensures the stream is ready
        log.info("waiting_for_greeting_trigger")
        await asyncio.wait_for(greeting_triggered.wait(), timeout=10.0)
        log.info("greeting_triggered_starting_audio_relay")

        async for audio_pcm in voice_session.receive_audio_stream():
            if first_audio_time is None:
                first_audio_time = time.time()
                latency = first_audio_time - start_time
                log.info(
                    "first_audio_from_provider",
                    latency_secs=round(latency, 2),
                    audio_bytes=len(audio_pcm),
                )

            try:
                # Convert PCM16 24kHz to μ-law 8kHz for Telnyx
                audio_mulaw = convert_openai_to_telnyx(audio_pcm, log)

                # Encode as base64
                audio_b64 = base64.b64encode(audio_mulaw).decode("utf-8")

                # Send to Telnyx in the expected JSON format
                message = json.dumps({
                    "event": "media",
                    "media": {"payload": audio_b64},
                })
                await websocket.send_text(message)

                audio_chunks_sent += 1
                total_audio_bytes += len(audio_mulaw)

                # Log periodically
                if audio_chunks_sent % 50 == 0:
                    elapsed = time.time() - start_time
                    log.debug(
                        "audio_relay_stats",
                        direction="provider_to_telnyx",
                        chunks=audio_chunks_sent,
                        total_bytes=total_audio_bytes,
                        elapsed_secs=round(elapsed, 1),
                    )

            except Exception as e:
                log.exception(
                    "provider_audio_conversion_error",
                    error=str(e),
                    audio_bytes=len(audio_pcm),
                )

    except TimeoutError:
        log.error("greeting_trigger_timeout", timeout_secs=10)
    except WebSocketDisconnect:
        elapsed = time.time() - start_time
        log.info(
            "telnyx_websocket_disconnected_while_sending",
            total_chunks=audio_chunks_sent,
            duration_secs=round(elapsed, 1),
        )
    except asyncio.CancelledError:
        log.info("provider_receive_cancelled")
        raise
    except Exception as e:
        log.exception(
            "receive_from_provider_error",
            error=str(e),
            chunks_sent=audio_chunks_sent,
        )
