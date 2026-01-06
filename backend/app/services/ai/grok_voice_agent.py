"""Grok (xAI) Realtime API integration for voice conversations.

Grok Voice Agent API is compatible with OpenAI Realtime API format.
Supports realism enhancements via auditory cues: [whisper], [sigh], [laugh], etc.
"""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from app.models.agent import Agent

logger = structlog.get_logger()

# Grok available voices
GROK_VOICES = {
    "ara": "Ara - Warm & friendly (female, default)",
    "rex": "Rex - Confident & clear (male)",
    "sal": "Sal - Smooth & balanced (neutral)",
    "eve": "Eve - Energetic & upbeat (female)",
    "leo": "Leo - Authoritative & strong (male)",
}

# Realism enhancement cues that can be used in prompts
GROK_REALISM_CUES = [
    "[whisper]",
    "[sigh]",
    "[laugh]",
    "[pause]",
    "[breath]",
]


class GrokVoiceAgentSession:
    """Grok (xAI) Realtime API session for voice conversations.

    Manages:
    - WebSocket connection to Grok Realtime API
    - Audio streaming and format conversion
    - Session configuration and context injection
    - Realism enhancements via auditory cues
    """

    BASE_URL = "wss://api.x.ai/v1/realtime"

    def __init__(self, api_key: str, agent: Agent | None = None) -> None:
        """Initialize Grok voice agent session.

        Args:
            api_key: xAI API key
            agent: Optional Agent model for configuration
        """
        self.api_key = api_key
        self.agent = agent
        self.ws: ClientConnection | None = None
        self.logger = logger.bind(service="grok_voice_agent")
        self._connection_task: asyncio.Task[None] | None = None

    async def connect(self) -> bool:
        """Connect to Grok Realtime API.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("connecting_to_grok_realtime_api")

        try:
            self.ws = await websockets.connect(
                self.BASE_URL,
                additional_headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            self.logger.info("connected_to_grok_realtime_api")

            # Send session configuration
            await self._configure_session()

            return True
        except Exception as e:
            self.logger.exception("grok_connection_failed", error=str(e))
            return False

    async def disconnect(self) -> None:
        """Disconnect from Grok Realtime API."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                self.logger.exception("grok_disconnect_error", error=str(e))
            self.ws = None

    def _enhance_prompt_with_realism(self, prompt: str) -> str:
        """Enhance system prompt with Grok realism instructions.

        Adds guidance for the model to use auditory cues naturally.

        Args:
            prompt: Original system prompt

        Returns:
            Enhanced prompt with realism instructions
        """
        realism_instructions = """

# Voice Realism Enhancements
You can use these auditory cues naturally in your responses to sound more human:
- [sigh] - Express mild frustration, relief, or thoughtfulness
- [laugh] - React to humor or express friendliness
- [whisper] - For confidential or emphasis moments
- Use these sparingly and naturally - don't overuse them.
"""
        return prompt + realism_instructions

    async def _configure_session(self) -> None:
        """Configure the Grok Realtime session with agent settings."""
        # Get base prompt
        base_prompt = (
            self.agent.system_prompt
            if self.agent
            else "You are a helpful AI voice assistant."
        )

        # Enhance with realism cues
        enhanced_prompt = self._enhance_prompt_with_realism(base_prompt)

        # Get voice - default to 'ara' for Grok
        voice = "ara"
        if self.agent and self.agent.voice_id:
            voice = self.agent.voice_id.lower()
            # Validate voice
            if voice not in GROK_VOICES:
                self.logger.warning(
                    "invalid_grok_voice",
                    voice=voice,
                    defaulting_to="ara",
                )
                voice = "ara"

        config: dict[str, Any] = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": enhanced_prompt,
                "voice": voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": self.agent.turn_detection_mode
                    if self.agent and self.agent.turn_detection_mode
                    else "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "temperature": self.agent.temperature if self.agent else 0.8,
            },
        }

        await self._send_event(config)
        self.logger.info("grok_session_configured", voice=voice)

    async def configure_session(
        self,
        voice: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        turn_detection_mode: str | None = None,
        turn_detection_threshold: float | None = None,
        silence_duration_ms: int | None = None,
    ) -> None:
        """Reconfigure the session with custom settings.

        Args:
            voice: Voice ID (ara, rex, sal, eve, leo)
            system_prompt: System instructions for the assistant
            temperature: Response temperature (0.0-1.0)
            turn_detection_mode: Turn detection type (server_vad, none)
            turn_detection_threshold: VAD threshold (0.0-1.0)
            silence_duration_ms: Silence duration before turn ends
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        session_config: dict[str, Any] = {}

        if voice:
            # Validate and normalize voice
            voice_lower = voice.lower()
            if voice_lower in GROK_VOICES:
                session_config["voice"] = voice_lower
            else:
                self.logger.warning("invalid_grok_voice", voice=voice)

        if system_prompt:
            session_config["instructions"] = self._enhance_prompt_with_realism(
                system_prompt
            )

        if temperature is not None:
            session_config["temperature"] = temperature

        # Configure turn detection
        if any([turn_detection_mode, turn_detection_threshold, silence_duration_ms]):
            turn_detection: dict[str, Any] = {
                "type": turn_detection_mode or "server_vad"
            }
            if turn_detection_threshold is not None:
                turn_detection["threshold"] = turn_detection_threshold
            if silence_duration_ms is not None:
                turn_detection["silence_duration_ms"] = silence_duration_ms
            turn_detection["prefix_padding_ms"] = 300
            session_config["turn_detection"] = turn_detection

        if session_config:
            config = {
                "type": "session.update",
                "session": session_config,
            }
            await self._send_event(config)
            self.logger.info(
                "grok_session_reconfigured", updates=list(session_config.keys())
            )

    async def send_greeting(self, greeting: str) -> None:
        """Send an initial greeting message.

        Args:
            greeting: The greeting text to speak
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": greeting,
                    }
                ],
            },
        }

        try:
            await self._send_event(event)

            # Request the assistant to respond
            response_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                },
            }
            await self._send_event(response_event)

            self.logger.info("grok_greeting_sent", greeting_length=len(greeting))
        except Exception as e:
            self.logger.exception("grok_send_greeting_error", error=str(e))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send audio chunk to Grok.

        Args:
            audio_data: PCM audio data (16-bit, 16kHz)
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        try:
            encoded = base64.b64encode(audio_data).decode("utf-8")

            event = {
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }

            await self._send_event(event)
        except Exception as e:
            self.logger.exception("grok_send_audio_error", error=str(e))

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        """Stream audio responses from Grok.

        Yields:
            PCM audio chunks (16-bit)
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")

                # Grok uses same event types as OpenAI Realtime
                if event_type == "response.audio.delta":
                    audio_data = event.get("delta", "")
                    if audio_data:
                        yield base64.b64decode(audio_data)

                elif event_type == "response.output_audio.delta":
                    # Alternative event name in Grok API
                    audio_data = event.get("delta", "")
                    if audio_data:
                        yield base64.b64decode(audio_data)

                elif event_type == "response.done":
                    self.logger.info("grok_response_complete")
                    break

                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(
                        "grok_realtime_error",
                        error_type=error.get("type"),
                        error_message=error.get("message"),
                    )
                    break

        except Exception as e:
            self.logger.exception("grok_receive_audio_error", error=str(e))

    async def inject_context(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
    ) -> None:
        """Inject conversation context into the session.

        Args:
            contact_info: Contact information (name, company, etc.)
            offer_info: Offer/product information
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        context_messages = []

        if contact_info:
            contact_msg = "Customer information:\n"
            if contact_info.get("name"):
                contact_msg += f"Name: {contact_info['name']}\n"
            if contact_info.get("company"):
                contact_msg += f"Company: {contact_info['company']}\n"
            context_messages.append(contact_msg)

        if offer_info:
            offer_msg = "Offer information:\n"
            if offer_info.get("name"):
                offer_msg += f"Offer: {offer_info['name']}\n"
            if offer_info.get("description"):
                offer_msg += f"Description: {offer_info['description']}\n"
            if offer_info.get("terms"):
                offer_msg += f"Terms: {offer_info['terms']}\n"
            context_messages.append(offer_msg)

        if context_messages:
            combined_context = "\n".join(context_messages)

            event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": combined_context,
                        }
                    ],
                },
            }

            try:
                await self._send_event(event)
                self.logger.info("grok_context_injected")
            except Exception as e:
                self.logger.exception("grok_inject_context_error", error=str(e))

    async def _send_event(self, event: dict[str, Any]) -> None:
        """Send event to WebSocket.

        Args:
            event: Event dictionary to send
        """
        if not self.ws:
            raise RuntimeError("Grok WebSocket not connected")

        try:
            await self.ws.send(json.dumps(event))
        except Exception as e:
            self.logger.exception("grok_send_event_error", error=str(e))
            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected.

        Returns:
            True if connected, False otherwise
        """
        if self.ws is None:
            return False
        try:
            return bool(getattr(self.ws, "open", False))
        except Exception:
            return False
