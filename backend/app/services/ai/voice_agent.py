"""OpenAI Realtime API integration for voice conversations."""

import asyncio
import base64
import binascii
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
        """Configure the Realtime session with agent settings.

        Uses pcm16 at 24kHz - the voice_bridge handles conversion from/to
        Telnyx's μ-law 8kHz format.
        """
        # Build system instructions - be explicit about role and behavior
        base_instructions = (
            self.agent.system_prompt
            if self.agent
            else "You are a helpful AI voice assistant."
        )

        # Add telephony-specific guidance to prevent hallucination at call start
        instructions = f"""{base_instructions}

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally and wait for response
- Do NOT generate random content, fun facts, or filler - stay focused on your purpose
- Speak clearly and conversationally as if on a real phone call"""

        config: dict[str, Any] = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "voice": self.agent.voice_id if self.agent else "alloy",
                # PCM16 at 24kHz - voice_bridge converts from/to Telnyx μ-law 8kHz
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": self.agent.turn_detection_mode
                    if self.agent and self.agent.turn_detection_mode
                    else "server_vad",
                    # Higher threshold = less sensitive to background noise
                    "threshold": 0.8,
                    # More padding before speech starts (prevents cutting off beginning)
                    "prefix_padding_ms": 500,
                    # Wait longer after silence before responding (prevents talking over)
                    "silence_duration_ms": 1000,
                },
                "temperature": 0.8,
            },
        }

        await self._send_event(config)
        self.logger.info("session_configured", audio_format="pcm16")

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
            # Add telephony guidance to custom prompts too
            enhanced_prompt = f"""{system_prompt}

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally and wait for response
- Do NOT generate random content, fun facts, or filler - stay focused on your purpose
- Speak clearly and conversationally as if on a real phone call"""
            session_config["instructions"] = enhanced_prompt

        if temperature is not None:
            session_config["temperature"] = temperature

        # Configure turn detection
        if any([turn_detection_mode, turn_detection_threshold, silence_duration_ms]):
            turn_detection: dict[str, Any] = {"type": turn_detection_mode or "server_vad"}
            if turn_detection_threshold is not None:
                turn_detection["threshold"] = turn_detection_threshold
            if silence_duration_ms is not None:
                turn_detection["silence_duration_ms"] = silence_duration_ms
            turn_detection["prefix_padding_ms"] = 500
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

        # Store the greeting for later use by trigger_initial_response
        self._pending_greeting = greeting

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

    async def trigger_initial_response(self, greeting: str | None = None) -> None:
        """Trigger the AI to start speaking with the initial greeting.

        Call this after the audio stream is established to initiate the conversation.
        Creates a user message prompting the AI to greet, then triggers response.create().

        Args:
            greeting: Optional greeting text. If not provided, uses the pending greeting
                     from send_greeting or agent's initial greeting.
        """
        if not self.ws:
            self.logger.warning("websocket_not_connected")
            return

        # Use provided greeting, or pending greeting, or agent's initial greeting
        message = greeting
        if not message and hasattr(self, "_pending_greeting"):
            message = self._pending_greeting
        if not message and self.agent and self.agent.initial_greeting:
            message = self.agent.initial_greeting

        try:
            # Create a user message that instructs the AI to deliver the greeting
            # This is the proven pattern from working OpenAI Realtime integrations
            if message:
                prompt_text = f"Greet the caller by saying: {message}"
            else:
                prompt_text = "Greet the caller and introduce yourself briefly."

            event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt_text,
                        }
                    ],
                },
            }

            await self._send_event(event)
            self.logger.info(
                "initial_response_triggered",
                has_greeting=bool(message),
                greeting_length=len(message) if message else 0,
            )

            # Trigger response generation - simple form without extra options
            # This tells OpenAI to respond to the conversation item we just created
            await self._send_event({"type": "response.create"})
            self.logger.info("response_requested")

        except Exception as e:
            self.logger.exception("trigger_response_error", error=str(e))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send audio chunk to OpenAI.

        Args:
            audio_data: PCM audio data (16-bit, 16kHz)
        """
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

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:  # noqa: PLR0912, PLR0915
        """Stream audio responses from OpenAI.

        This generator continuously yields audio chunks from the OpenAI Realtime API.
        It does NOT break on response.done - instead it keeps listening for more
        responses as the conversation continues.

        Yields:
            PCM audio chunks (16-bit, 16kHz)
        """
        if not self.ws:
            self.logger.warning("websocket_not_connected_for_audio_stream")
            return

        audio_chunks_received = 0
        total_audio_bytes = 0
        responses_completed = 0

        try:
            self.logger.info("starting_audio_receive_stream")

            async for message in self.ws:
                # Parse JSON with error handling to prevent stream crash
                try:
                    event = json.loads(message)
                except json.JSONDecodeError as e:
                    self.logger.warning(
                        "invalid_json_from_openai",
                        error=str(e),
                        message_preview=str(message)[:100],
                    )
                    continue

                event_type = event.get("type", "")

                if event_type == "response.audio.delta":
                    # Audio chunk received
                    audio_data = event.get("delta", "")
                    if audio_data:
                        # Decode base64 with error handling
                        try:
                            decoded = base64.b64decode(audio_data)
                        except (binascii.Error, ValueError) as e:
                            self.logger.warning(
                                "invalid_base64_audio_from_openai",
                                error=str(e),
                            )
                            continue

                        audio_chunks_received += 1
                        total_audio_bytes += len(decoded)

                        # Log periodically
                        if audio_chunks_received % 100 == 0:
                            self.logger.debug(
                                "audio_stream_progress",
                                chunks=audio_chunks_received,
                                total_bytes=total_audio_bytes,
                                responses=responses_completed,
                            )

                        yield decoded

                elif event_type == "response.audio_transcript.delta":
                    # Transcript chunk - log for debugging
                    transcript = event.get("delta", "")
                    if transcript:
                        self.logger.debug("transcript_chunk", text=transcript[:50])

                elif event_type == "response.done":
                    # Response complete - but DON'T break!
                    # Keep listening for more responses in the conversation
                    responses_completed += 1
                    self.logger.info(
                        "response_completed",
                        response_num=responses_completed,
                        total_audio_chunks=audio_chunks_received,
                        total_audio_bytes=total_audio_bytes,
                    )
                    # Continue listening for next response

                elif event_type == "input_audio_buffer.speech_started":
                    self.logger.debug("user_speech_started")

                elif event_type == "input_audio_buffer.speech_stopped":
                    self.logger.debug("user_speech_stopped")

                elif event_type == "input_audio_buffer.committed":
                    self.logger.debug("audio_buffer_committed")

                elif event_type == "conversation.item.created":
                    item = event.get("item", {})
                    self.logger.debug(
                        "conversation_item_created",
                        item_type=item.get("type"),
                        role=item.get("role"),
                    )

                elif event_type == "response.created":
                    self.logger.debug("response_created")

                elif event_type == "response.output_item.added":
                    self.logger.debug("response_output_item_added")

                elif event_type == "response.content_part.added":
                    self.logger.debug("response_content_part_added")

                elif event_type == "session.created":
                    session = event.get("session", {})
                    self.logger.info(
                        "session_created",
                        session_id=session.get("id"),
                        model=session.get("model"),
                    )

                elif event_type == "session.updated":
                    self.logger.debug("session_updated")

                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(
                        "openai_realtime_error",
                        error_type=error.get("type"),
                        error_message=error.get("message"),
                        error_code=error.get("code"),
                    )
                    # Don't break - some errors are recoverable

                elif event_type == "rate_limits.updated":
                    self.logger.debug(
                        "rate_limits_updated",
                        limits=event.get("rate_limits", []),
                    )

                else:
                    # Log unknown event types for debugging
                    self.logger.debug("openai_event", event_type=event_type)

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "openai_websocket_closed",
                code=e.code,
                reason=e.reason,
                chunks_received=audio_chunks_received,
            )
        except Exception as e:
            self.logger.exception(
                "receive_audio_stream_error",
                error=str(e),
                chunks_received=audio_chunks_received,
            )

        self.logger.info(
            "audio_stream_ended",
            total_chunks=audio_chunks_received,
            total_bytes=total_audio_bytes,
            total_responses=responses_completed,
        )

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
