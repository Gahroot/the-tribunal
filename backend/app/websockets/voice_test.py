"""Voice test WebSocket endpoint for browser-based agent testing."""

import asyncio
import base64
import contextlib
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.ai.grok_voice_agent import GrokVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession

router = APIRouter()
logger = structlog.get_logger()


async def _get_agent_by_id(agent_id: str, workspace_id: str, log: Any) -> Any:
    """Look up an agent by ID.

    Args:
        agent_id: Agent UUID
        workspace_id: Workspace UUID
        log: Logger instance

    Returns:
        Agent model or None
    """
    from sqlalchemy import select

    from app.models.agent import Agent

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.workspace_id == workspace_id,
            )
        )
        agent = result.scalar_one_or_none()
        if agent:
            log.info("found_agent", agent_id=str(agent.id), agent_name=agent.name)
        return agent


def _create_voice_session_for_test(
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


async def _handle_start_message(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    agent: Any,
    voice_provider: str,
    log: Any,
) -> asyncio.Task[None] | None:
    """Handle the start message from client.

    Returns:
        Task for receiving audio, or None if connection failed
    """
    if not await voice_session.connect():
        log.error("failed_to_connect_to_voice_provider")
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to connect to {voice_provider}",
        })
        return None

    log.info("voice_session_connected")

    # Configure session with agent settings
    await voice_session.configure_session(
        voice=agent.voice_id,
        system_prompt=agent.system_prompt,
        temperature=agent.temperature,
    )

    await websocket.send_json({"type": "connected"})

    # Start receiving audio from provider
    receive_task = asyncio.create_task(
        _receive_from_provider(websocket, voice_session, log)
    )

    # Trigger initial greeting if configured
    if agent.initial_greeting:
        await voice_session.trigger_initial_response(agent.initial_greeting)

    return receive_task


async def _handle_audio_message(
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    message: dict[str, Any],
) -> None:
    """Handle audio message from client."""
    audio_b64 = message.get("data", "")
    if audio_b64:
        audio_pcm = base64.b64decode(audio_b64)
        await voice_session.send_audio_chunk(audio_pcm)


async def _process_messages(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    agent: Any,
    voice_provider: str,
    log: Any,
) -> None:
    """Process incoming messages from the client.

    Args:
        websocket: WebSocket connection
        voice_session: Voice provider session
        agent: Agent model
        voice_provider: Provider name
        log: Logger instance
    """
    session_active = False
    receive_task: asyncio.Task[None] | None = None

    try:
        while True:
            raw_data = await websocket.receive_text()
            message = json.loads(raw_data)
            msg_type = message.get("type", "")

            if msg_type == "start" and not session_active:
                receive_task = await _handle_start_message(
                    websocket, voice_session, agent, voice_provider, log
                )
                if receive_task:
                    session_active = True

            elif msg_type == "audio" and session_active:
                await _handle_audio_message(voice_session, message)

            elif msg_type == "stop":
                log.info("stop_requested")
                break

    except WebSocketDisconnect:
        log.info("websocket_disconnected")
    except json.JSONDecodeError as e:
        log.warning("invalid_json", error=str(e))
    finally:
        if receive_task:
            receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receive_task


@router.websocket("/voice/test/{workspace_id}/{agent_id}")
async def voice_test_endpoint(
    websocket: WebSocket,
    workspace_id: str,
    agent_id: str,
) -> None:
    """WebSocket endpoint for browser-based voice agent testing.

    Protocol:
    - Client sends JSON messages with type field
    - Server sends JSON messages with type field

    Client -> Server:
        {"type": "start"} - Start the voice session
        {"type": "audio", "data": "<base64-pcm16>"} - Send audio chunk
        {"type": "stop"} - Stop the session

    Server -> Client:
        {"type": "connected"} - Session connected to voice provider
        {"type": "audio", "data": "<base64-pcm16>"} - Audio response
        {"type": "transcript", "role": "user"|"assistant", "text": "..."} - Transcript
        {"type": "error", "message": "..."} - Error message
        {"type": "stopped"} - Session stopped

    Args:
        websocket: WebSocket connection from browser
        workspace_id: Workspace UUID
        agent_id: Agent UUID to test
    """
    log = logger.bind(
        endpoint="voice_test",
        workspace_id=workspace_id,
        agent_id=agent_id,
    )
    log.info("voice_test_connection_received")

    await websocket.accept()

    # Look up the agent
    agent = await _get_agent_by_id(agent_id, workspace_id, log)
    if not agent:
        await websocket.send_json({"type": "error", "message": "Agent not found"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Determine voice provider
    voice_provider = agent.voice_provider.lower() if agent.voice_provider else "openai"
    log.info("using_voice_provider", provider=voice_provider)

    # Create voice session
    voice_session, error = _create_voice_session_for_test(voice_provider, agent)
    if voice_session is None:
        log.error("api_key_not_configured", provider=voice_provider)
        await websocket.send_json({"type": "error", "message": error})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        await _process_messages(websocket, voice_session, agent, voice_provider, log)
    except Exception as e:
        log.exception("voice_test_error", error=str(e))
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await voice_session.disconnect()
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "stopped"})
            await websocket.close()
        log.info("voice_test_session_ended")


async def _receive_from_provider(
    websocket: WebSocket,
    voice_session: VoiceAgentSession | GrokVoiceAgentSession,
    log: Any,
) -> None:
    """Receive audio from voice provider and send to browser.

    Args:
        websocket: Browser WebSocket connection
        voice_session: Voice provider session
        log: Logger instance
    """
    try:
        async for audio_pcm in voice_session.receive_audio_stream():
            audio_b64 = base64.b64encode(audio_pcm).decode("utf-8")
            await websocket.send_json({
                "type": "audio",
                "data": audio_b64,
            })
    except asyncio.CancelledError:
        log.info("receive_task_cancelled")
    except Exception as e:
        log.exception("receive_from_provider_error", error=str(e))
