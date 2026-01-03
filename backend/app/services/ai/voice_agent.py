"""OpenAI Realtime API integration for voice conversations."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from app.models.agent import Agent

logger = structlog.get_logger()


class VoiceAgentSession:
    """OpenAI Realtime API session for voice conversations.

    Manages:
    - WebSocket connection to OpenAI Realtime API
    - Audio streaming and format conversion
    - Session configuration and context injection
    - Conversation state management
    """

    BASE_URL = "wss://api.openai.com/v1/realtime"
    MODEL = "gpt-4o-realtime-preview-2024-12-26"

    def __init__(self, api_key: str, agent: Agent | None = None) -> None:
        """Initialize voice agent session.

        Args:
            api_key: OpenAI API key
            agent: Optional Agent model for configuration
        """
        self.api_key = api_key
        self.agent = agent
        self.ws: ClientConnection | None = None
        self.logger = logger.bind(service="voice_agent")
        self._connection_task: asyncio.Task[None] | None = None

    async def connect(self) -> bool:
        """Connect to OpenAI Realtime API.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("connecting_to_realtime_api")

        try:
            # Build connection URL with API key
            url = f"{self.BASE_URL}?model={self.MODEL}"

            self.ws = await websockets.connect(
                url,
                additional_headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "OpenAI-Beta": "realtime=v1",
                },
            )

            self.logger.info("connected_to_realtime_api")

            # Send session configuration
            await self._configure_session()

            return True
        except Exception as e:
            self.logger.exception("connection_failed", error=str(e))
            return False

    async def disconnect(self) -> None:
        """Disconnect from OpenAI Realtime API."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                self.logger.exception("disconnect_error", error=str(e))
            self.ws = None

    async def _configure_session(self) -> None:
        """Configure the Realtime session with agent settings."""
        config: dict[str, Any] = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "model": self.MODEL,
                "instructions": self.agent.system_prompt
                if self.agent
                else "You are a helpful AI voice assistant.",
                "voice": self.agent.voice_id
                if self.agent
                else "alloy",  # Default voice
                "input_audio_format": "pcm16",
                "input_audio_sample_rate": 16000,
                "output_audio_format": "pcm16",
                "output_audio_sample_rate": 16000,
                "turn_detection": {
                    "type": self.agent.turn_detection_mode
                    if self.agent
                    else "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                } if not self.agent or self.agent.turn_detection_mode else {
                    "type": "server_vad"
                },
                "temperature": 0.8,
            },
        }

        await self._send_event(config)
        self.logger.info("session_configured")

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

        This method allows updating session settings after connection.

        Args:
            voice: Voice ID (alloy, shimmer, nova, etc.)
            system_prompt: System instructions for the assistant
            temperature: Response temperature (0.0-1.0)
            turn_detection_mode: Turn detection type (server_vad, none)
            turn_detection_threshold: VAD threshold (0.0-1.0)
            silence_duration_ms: Silence duration before turn ends
        """
        if not self.ws:
            self.logger.warning("websocket_not_connected")
            return

        session_config: dict[str, Any] = {}

        if voice:
            session_config["voice"] = voice
        if system_prompt:
            session_config["instructions"] = system_prompt
        if temperature is not None:
            session_config["temperature"] = temperature

        # Configure turn detection
        if any([turn_detection_mode, turn_detection_threshold, silence_duration_ms]):
            turn_detection: dict[str, Any] = {"type": turn_detection_mode or "server_vad"}
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
            self.logger.info("session_reconfigured", updates=list(session_config.keys()))

    async def send_greeting(self, greeting: str) -> None:
        """Send an initial greeting message.

        This sends a text message that will be spoken by the assistant.

        Args:
            greeting: The greeting text to speak
        """
        if not self.ws:
            self.logger.warning("websocket_not_connected")
            return

        # Create a conversation item with the greeting as assistant message
        # and trigger response generation
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

            # Request the assistant to respond (which will speak the greeting)
            response_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                },
            }
            await self._send_event(response_event)

            self.logger.info("greeting_sent", greeting_length=len(greeting))
        except Exception as e:
            self.logger.exception("send_greeting_error", error=str(e))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send audio chunk to OpenAI.

        Args:
            audio_data: PCM audio data (16-bit, 16kHz)
        """
        import base64

        if not self.ws:
            self.logger.warning("websocket_not_connected")
            return

        try:
            # Encode audio as base64
            encoded = base64.b64encode(audio_data).decode("utf-8")

            event = {
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }

            await self._send_event(event)
        except Exception as e:
            self.logger.exception("send_audio_error", error=str(e))

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        """Stream audio responses from OpenAI.

        Yields:
            PCM audio chunks (16-bit, 16kHz)
        """
        if not self.ws:
            self.logger.warning("websocket_not_connected")
            return

        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "response.audio.delta":
                    import base64

                    audio_data = event.get("delta", "")
                    if audio_data:
                        yield base64.b64decode(audio_data)

                elif event_type == "response.done":
                    self.logger.info("response_complete")
                    break

                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(
                        "realtime_error",
                        error_type=error.get("type"),
                        error_message=error.get("message"),
                    )
                    break

        except Exception as e:
            self.logger.exception("receive_audio_error", error=str(e))

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
            self.logger.warning("websocket_not_connected")
            return

        context_messages = []

        # Add contact context
        if contact_info:
            contact_msg = "Customer information:\n"
            if contact_info.get("name"):
                contact_msg += f"Name: {contact_info['name']}\n"
            if contact_info.get("company"):
                contact_msg += f"Company: {contact_info['company']}\n"
            context_messages.append(contact_msg)

        # Add offer context
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
                self.logger.info("context_injected")
            except Exception as e:
                self.logger.exception("inject_context_error", error=str(e))

    async def _send_event(self, event: dict[str, Any]) -> None:
        """Send event to WebSocket.

        Args:
            event: Event dictionary to send
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        try:
            await self.ws.send(json.dumps(event))
        except Exception as e:
            self.logger.exception("send_event_error", error=str(e))
            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected.

        Returns:
            True if connected, False otherwise
        """
        if self.ws is None:
            return False
        try:
            # websockets library uses 'open' property to check connection state
            return bool(getattr(self.ws, "open", False))
        except Exception:
            return False
