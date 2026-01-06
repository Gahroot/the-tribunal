"""Voice bridge WebSocket endpoint for Telnyx media streaming."""

import asyncio
import base64
import contextlib
import struct
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.ai.grok_voice_agent import GrokVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession

router = APIRouter()
logger = structlog.get_logger()

# Conversion utilities for audio formats
# Telnyx uses μ-law (G.711), OpenAI uses PCM16


def mulaw_to_pcm(data: bytes) -> bytes:
    """Convert μ-law audio to PCM16.

    Args:
        data: μ-law encoded audio bytes

    Returns:
        PCM16 audio bytes
    """
    # μ-law to PCM lookup table
    mulaw_table = [
        -32124,
        -31100,
        -30076,
        -29052,
        -28028,
        -27004,
        -25980,
        -24956,
        -23932,
        -22908,
        -21884,
        -20860,
        -19836,
        -18812,
        -17788,
        -16764,
        -15996,
        -15484,
        -14972,
        -14460,
        -13948,
        -13436,
        -12924,
        -12412,
        -11900,
        -11388,
        -10876,
        -10364,
        -9852,
        -9340,
        -8828,
        -8316,
        -7932,
        -7676,
        -7420,
        -7164,
        -6908,
        -6652,
        -6396,
        -6140,
        -5884,
        -5628,
        -5372,
        -5116,
        -4860,
        -4604,
        -4348,
        -4092,
        -3900,
        -3772,
        -3644,
        -3516,
        -3388,
        -3260,
        -3132,
        -3004,
        -2876,
        -2748,
        -2620,
        -2492,
        -2364,
        -2236,
        -2108,
        -1980,
        -1884,
        -1820,
        -1756,
        -1692,
        -1628,
        -1564,
        -1500,
        -1436,
        -1372,
        -1308,
        -1244,
        -1180,
        -1116,
        -1052,
        -988,
        -924,
        -876,
        -844,
        -812,
        -780,
        -748,
        -716,
        -684,
        -652,
        -620,
        -588,
        -556,
        -524,
        -492,
        -460,
        -428,
        -396,
        -372,
        -356,
        -340,
        -324,
        -308,
        -292,
        -276,
        -260,
        -244,
        -228,
        -212,
        -196,
        -180,
        -164,
        -148,
        -132,
        -120,
        -112,
        -104,
        -96,
        -88,
        -80,
        -72,
        -64,
        -56,
        -48,
        -40,
        -32,
        -24,
        -16,
        -8,
        0,
        32124,
        31100,
        30076,
        29052,
        28028,
        27004,
        25980,
        24956,
        23932,
        22908,
        21884,
        20860,
        19836,
        18812,
        17788,
        16764,
        15996,
        15484,
        14972,
        14460,
        13948,
        13436,
        12924,
        12412,
        11900,
        11388,
        10876,
        10364,
        9852,
        9340,
        8828,
        8316,
        7932,
        7676,
        7420,
        7164,
        6908,
        6652,
        6396,
        6140,
        5884,
        5628,
        5372,
        5116,
        4860,
        4604,
        4348,
        4092,
        3900,
        3772,
        3644,
        3516,
        3388,
        3260,
        3132,
        3004,
        2876,
        2748,
        2620,
        2492,
        2364,
        2236,
        2108,
        1980,
        1884,
        1820,
        1756,
        1692,
        1628,
        1564,
        1500,
        1436,
        1372,
        1308,
        1244,
        1180,
        1116,
        1052,
        988,
        924,
        876,
        844,
        812,
        780,
        748,
        716,
        684,
        652,
        620,
        588,
        556,
        524,
        492,
        460,
        428,
        396,
        372,
        356,
        340,
        324,
        308,
        292,
        276,
        260,
        244,
        228,
        212,
        196,
        180,
        164,
        148,
        132,
        120,
        112,
        104,
        96,
        88,
        80,
        72,
        64,
        56,
        48,
        40,
        32,
        24,
        16,
        8,
    ]

    pcm_data = b""
    for byte in data:
        pcm_value = mulaw_table[byte]
        # Convert to little-endian 16-bit signed integer
        pcm_data += struct.pack("<h", pcm_value)

    return pcm_data


def pcm_to_mulaw(data: bytes) -> bytes:
    """Convert PCM16 audio to μ-law.

    Args:
        data: PCM16 audio bytes (little-endian)

    Returns:
        μ-law encoded audio bytes
    """
    mulaw_data = b""

    # Process 2 bytes at a time (16-bit samples)
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            # Unpack little-endian signed 16-bit integer
            sample = struct.unpack("<h", data[i : i + 2])[0]

            # Simple μ-law encoding (simplified version)
            # Full implementation would use proper bit manipulation
            clamped = max(-32768, min(32767, sample))
            magnitude = abs(clamped)

            # Find exponent
            exponent = 0
            mantissa = magnitude
            if magnitude > 255:
                for exp in range(8):
                    if magnitude <= 0xFF << (exp + 1):
                        exponent = exp
                        break
            else:
                exponent = 0

            mantissa = (magnitude >> (exponent + 3)) & 0x0F

            # Combine exponent and mantissa
            byte_val = (exponent << 4) | mantissa

            # Add sign and complement
            if clamped < 0:
                byte_val ^= 0x80

            mulaw_data += bytes([byte_val ^ 0xFF])

    return mulaw_data


async def _lookup_call_context(
    call_id: str,
    log: Any,
) -> tuple[Any, dict[str, Any] | None, dict[str, Any] | None]:
    """Look up agent, contact, and offer context for a call.

    Args:
        call_id: Telnyx call control ID (provider_message_id)
        log: Logger instance

    Returns:
        Tuple of (agent, contact_info dict, offer_info dict)
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.agent import Agent
    from app.models.campaign import CampaignContact
    from app.models.contact import Contact
    from app.models.conversation import Message
    from app.models.offer import Offer

    agent = None
    contact_info = None
    offer_info = None

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
            return agent, contact_info, offer_info

        conversation = message.conversation

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

    return agent, contact_info, offer_info


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
        return GrokVoiceAgentSession(settings.xai_api_key, agent), None

    # Default to OpenAI
    if not settings.openai_api_key:
        return None, "OpenAI API key not configured"
    return VoiceAgentSession(settings.openai_api_key, agent), None


async def _setup_voice_session(
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    agent: Any,
    contact_info: dict[str, Any] | None,
    offer_info: dict[str, Any] | None,
    log: Any,
) -> None:
    """Configure voice session with agent settings and context.

    Args:
        voice_session: Voice provider session
        agent: Agent model for configuration
        contact_info: Contact information dict
        offer_info: Offer information dict
        log: Logger instance
    """
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

    if agent and agent.initial_greeting:
        await voice_session.send_greeting(agent.initial_greeting)
        log.info("initial_greeting_sent")


@router.websocket("/voice/stream/{call_id}")
async def voice_stream_bridge(websocket: WebSocket, call_id: str) -> None:
    """Bridge between Telnyx media stream and voice AI provider.

    Supports multiple providers:
    - OpenAI Realtime API (default)
    - Grok (xAI) Realtime API

    Args:
        websocket: WebSocket connection from Telnyx
        call_id: Telnyx call control ID
    """
    log = logger.bind(endpoint="voice_stream_bridge", call_id=call_id)
    log.info("voice_bridge_connection_received")

    await websocket.accept()

    # Get agent and conversation context from database first to determine provider
    agent, contact_info, offer_info = await _lookup_call_context(call_id, log)

    # Determine which voice provider to use
    voice_provider = "openai"  # default
    if agent and agent.voice_provider:
        voice_provider = agent.voice_provider.lower()

    log.info("using_voice_provider", provider=voice_provider)

    # Create appropriate voice session based on provider
    voice_session, error = _create_voice_session(voice_provider, agent)
    if voice_session is None:
        log.error("api_key_not_configured", provider=voice_provider)
        await websocket.send_json({"error": error})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        # Connect to voice provider
        if not await voice_session.connect():
            log.error("failed_to_connect_to_voice_provider", provider=voice_provider)
            await websocket.send_json(
                {"error": f"Failed to connect to {voice_provider} Realtime API"}
            )
            await websocket.close(code=status.WS_1011_SERVER_ERROR)
            return

        log.info("connected_to_voice_provider", provider=voice_provider)

        # Configure session with agent settings and inject context
        await _setup_voice_session(voice_session, agent, contact_info, offer_info, log)

        # Start bidirectional audio relay
        relay_task = asyncio.create_task(
            _relay_audio(websocket, voice_session, log)
        )

        try:
            # Keep connection alive
            while True:
                await asyncio.sleep(0.1)
                if not voice_session.is_connected():
                    log.warning("voice_provider_connection_lost")
                    break
        except asyncio.CancelledError:
            log.info("relay_cancelled")
        finally:
            relay_task.cancel()

    except WebSocketDisconnect:
        log.info("websocket_disconnected")
    except Exception as e:
        log.exception("voice_bridge_error", error=str(e))
    finally:
        await voice_session.disconnect()
        with contextlib.suppress(Exception):
            await websocket.close()


async def _relay_audio(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
) -> None:
    """Relay audio between Telnyx and OpenAI.

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: OpenAI Realtime session
        log: Logger instance
    """
    # Create tasks for bidirectional streaming
    send_task = asyncio.create_task(
        _receive_from_telnyx_and_send_to_provider(
            websocket, voice_session, log
        )
    )
    recv_task = asyncio.create_task(
        _receive_from_provider_and_send_to_telnyx(
            websocket, voice_session, log
        )
    )

    try:
        # Wait for either task to fail
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()

        # Check for exceptions
        for task in done:
            task.result()  # Raises exception if any

    except asyncio.CancelledError:
        log.info("relay_cancelled")
    except Exception as e:
        log.exception("relay_error", error=str(e))


async def _receive_from_telnyx_and_send_to_provider(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
) -> None:
    """Receive audio from Telnyx and send to voice provider.

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: Voice provider session (OpenAI or Grok)
        log: Logger instance
    """
    try:
        while True:
            # Receive audio data from Telnyx (base64-encoded μ-law)
            data = await websocket.receive_text()

            try:
                # Decode base64
                audio_mulaw = base64.b64decode(data)

                # Convert μ-law to PCM16
                audio_pcm = mulaw_to_pcm(audio_mulaw)

                # Send to OpenAI
                await voice_session.send_audio_chunk(audio_pcm)

            except Exception as e:
                log.exception(
                    "audio_conversion_error",
                    error=str(e),
                )

    except WebSocketDisconnect:
        log.info("telnyx_websocket_disconnected")
    except Exception as e:
        log.exception("receive_from_telnyx_error", error=str(e))


async def _receive_from_provider_and_send_to_telnyx(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
) -> None:
    """Receive audio from voice provider and send to Telnyx.

    Args:
        websocket: Telnyx WebSocket connection
        voice_session: Voice provider session (OpenAI or Grok)
        log: Logger instance
    """
    try:
        async for audio_pcm in voice_session.receive_audio_stream():
            try:
                # Convert PCM16 to μ-law
                audio_mulaw = pcm_to_mulaw(audio_pcm)

                # Encode as base64
                audio_b64 = base64.b64encode(audio_mulaw).decode("utf-8")

                # Send to Telnyx
                await websocket.send_text(audio_b64)

            except Exception as e:
                log.exception(
                    "audio_conversion_error",
                    error=str(e),
                )

    except WebSocketDisconnect:
        log.info("telnyx_websocket_disconnected_recv")
    except Exception as e:
        log.exception("receive_from_openai_error", error=str(e))
