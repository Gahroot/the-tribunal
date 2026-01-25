"""ElevenLabs Voice Agent - Hybrid architecture using Grok STT+LLM with ElevenLabs TTS.

This composite session provides:
- Grok Realtime API for Speech-to-Text and LLM (with tool calling for Cal.com)
- ElevenLabs for Text-to-Speech (expressive, high-quality voice output)

Architecture:
    Telnyx Audio In → Grok (STT+LLM+Tools) → Text → ElevenLabs TTS → Telnyx Audio Out
"""

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from app.models.agent import Agent
from app.services.ai.elevenlabs_tts import ElevenLabsTTSSession, get_voice_id
from app.services.ai.grok_voice_agent import GROK_BUILTIN_TOOLS, VOICE_BOOKING_TOOLS

logger = structlog.get_logger()


class ElevenLabsVoiceAgentSession:
    """Hybrid voice agent using Grok STT+LLM with ElevenLabs TTS.

    This session:
    - Connects to Grok Realtime API for speech recognition and LLM processing
    - Connects to ElevenLabs for text-to-speech synthesis
    - Routes input audio to Grok for STT
    - Intercepts Grok's text responses (ignoring Grok's audio)
    - Streams text to ElevenLabs for expressive voice synthesis
    - Returns ElevenLabs audio (ulaw_8000, ready for Telnyx)

    Key benefits:
    - Tool calling preserved (Cal.com booking, web search, X search)
    - ElevenLabs outputs ulaw_8000 directly (no conversion needed)
    - Access to 100+ ElevenLabs voices with rich expressiveness
    """

    GROK_BASE_URL = "wss://api.x.ai/v1/realtime"

    def __init__(
        self,
        xai_api_key: str,
        elevenlabs_api_key: str,
        agent: Agent | None = None,
        enable_tools: bool = False,
        timezone: str = "America/New_York",
    ) -> None:
        """Initialize hybrid voice agent session.

        Args:
            xai_api_key: xAI (Grok) API key for STT+LLM
            elevenlabs_api_key: ElevenLabs API key for TTS
            agent: Optional Agent model for configuration
            enable_tools: Enable Cal.com booking tools
            timezone: Timezone for date context (default: America/New_York)
        """
        self.xai_api_key = xai_api_key
        self.elevenlabs_api_key = elevenlabs_api_key
        self.agent = agent
        self._enable_tools = enable_tools
        self._timezone = timezone
        self.logger = logger.bind(service="elevenlabs_voice_agent")

        # Grok WebSocket for STT+LLM
        self.grok_ws: ClientConnection | None = None

        # ElevenLabs TTS session
        self._tts_session: ElevenLabsTTSSession | None = None

        # Tool call handling (delegated to callback)
        self._tool_callback: Callable[[str, str, dict[str, Any]], Any] | None = None
        self._pending_function_calls: dict[str, dict[str, Any]] = {}

        # Audio output queue (ElevenLabs ulaw audio)
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        # Task management
        self._grok_receive_task: asyncio.Task[None] | None = None
        self._tts_receive_task: asyncio.Task[None] | None = None

        # Text buffer for streaming to TTS
        self._text_buffer = ""
        self._text_buffer_lock = asyncio.Lock()

    def set_tool_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], Any],
    ) -> None:
        """Set callback for tool execution.

        Args:
            callback: Async function(call_id, function_name, arguments) -> result
        """
        self._tool_callback = callback

    async def connect(self) -> bool:
        """Connect to both Grok and ElevenLabs.

        Returns:
            True if both connections successful, False otherwise
        """
        self.logger.info("connecting_to_hybrid_voice_agent")

        try:
            # Connect to Grok Realtime API
            self.logger.info("connecting_to_grok_stt_llm")
            self.grok_ws = await websockets.connect(
                self.GROK_BASE_URL,
                additional_headers={
                    "Authorization": f"Bearer {self.xai_api_key}",
                },
            )
            self.logger.info("connected_to_grok")

            # Determine ElevenLabs voice ID
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default: Rachel
            if self.agent and self.agent.voice_id:
                voice_id = get_voice_id(self.agent.voice_id)

            # Connect to ElevenLabs TTS
            self.logger.info("connecting_to_elevenlabs_tts", voice_id=voice_id)
            self._tts_session = ElevenLabsTTSSession(
                api_key=self.elevenlabs_api_key,
                voice_id=voice_id,
            )

            if not await self._tts_session.connect(output_format="ulaw_8000"):
                self.logger.error("elevenlabs_connection_failed")
                await self._cleanup_grok()
                return False

            self.logger.info("connected_to_elevenlabs")

            # Configure Grok session (text output only - we ignore audio)
            await self._configure_grok_session()

            # Start background tasks
            self._grok_receive_task = asyncio.create_task(self._receive_from_grok())
            self._tts_receive_task = asyncio.create_task(self._receive_from_tts())

            self.logger.info("hybrid_voice_agent_connected")
            return True

        except Exception as e:
            self.logger.exception("hybrid_connection_failed", error=str(e))
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from both Grok and ElevenLabs."""
        self.logger.info("disconnecting_hybrid_voice_agent")

        # Cancel background tasks
        if self._grok_receive_task and not self._grok_receive_task.done():
            self._grok_receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._grok_receive_task

        if self._tts_receive_task and not self._tts_receive_task.done():
            self._tts_receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tts_receive_task

        # Disconnect ElevenLabs
        if self._tts_session:
            await self._tts_session.disconnect()
            self._tts_session = None

        # Disconnect Grok
        await self._cleanup_grok()

        # Signal end of audio stream
        await self._audio_queue.put(None)

        self.logger.info("hybrid_voice_agent_disconnected")

    async def _cleanup_grok(self) -> None:
        """Clean up Grok WebSocket connection."""
        if self.grok_ws:
            try:
                await self.grok_ws.close()
            except Exception as e:
                self.logger.exception("grok_disconnect_error", error=str(e))
            self.grok_ws = None

    def _enhance_prompt_with_realism(self, prompt: str) -> str:
        """Enhance system prompt with Grok realism instructions.

        Args:
            prompt: Original system prompt

        Returns:
            Enhanced prompt with realism instructions
        """
        realism_instructions = """

# Voice Realism Enhancements
You can use these cues naturally in your responses to sound more human:
- [sigh] - Express mild frustration, relief, or thoughtfulness
- [laugh] - React to humor or express friendliness
- Use these sparingly and naturally - don't overuse them.
Note: These cues will be interpreted by the speech synthesis system."""
        return prompt + realism_instructions

    def _get_date_context(self) -> str:
        """Get the date context string for the system prompt.

        Uses the timezone stored on the session (from workspace settings).
        Based on LiveKit's production voice agent pattern.

        Returns:
            Date context string to prepend to prompts
        """
        try:
            tz = ZoneInfo(self._timezone)
        except Exception:
            tz = ZoneInfo("America/New_York")

        now = datetime.now(tz)
        current_time = now.strftime("%A, %B %d, %Y at %I:%M %p")

        return f"The current date and time is {current_time}.\n\n"

    def _get_search_tools_guidance(self) -> str:
        """Get system prompt guidance for search tools."""
        if not self.agent or not self.agent.enabled_tools:
            return ""

        enabled = self.agent.enabled_tools
        has_web_search = "web_search" in enabled
        has_x_search = "x_search" in enabled

        if not has_web_search and not has_x_search:
            return ""

        guidance_parts = ["\n\n# Search Capabilities"]

        if has_web_search:
            guidance_parts.append(
                "You have access to real-time web search. "
                "Use it when users ask about current events, prices, news, weather, "
                "facts you're unsure about, or anything that requires up-to-date information."
            )

        if has_x_search:
            guidance_parts.append(
                "You have access to X (Twitter) search. "
                "Use it when users ask about trending topics, public opinions, "
                "what people are saying about something, or recent posts."
            )

        return "\n".join(guidance_parts)

    async def _configure_grok_session(self) -> None:
        """Configure Grok session for text output (we handle TTS separately)."""
        if not self.grok_ws:
            return

        # Build date context FIRST - this must be at the top of the prompt
        date_context = self._get_date_context()

        # Get base prompt
        base_prompt = (
            self.agent.system_prompt
            if self.agent
            else "You are a helpful AI voice assistant."
        )

        # Add identity prefix
        if self.agent and self.agent.name:
            agent_name = self.agent.name
            identity_prefix = (
                f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
                f"You MUST always identify yourself as {agent_name} - never use "
                "any other name. This is non-negotiable.\n\n"
            )
            base_prompt = identity_prefix + base_prompt

        # Combine: date context (top) + base prompt
        enhanced_prompt = date_context + base_prompt

        # Enhance prompt
        enhanced_prompt = self._enhance_prompt_with_realism(enhanced_prompt)
        enhanced_prompt += self._get_search_tools_guidance()

        # Add telephony guidance
        enhanced_prompt += """

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally
- Do NOT generate random content, fun facts, or filler
- Speak clearly and conversationally"""

        # Add booking instructions when tools are enabled
        if self._enable_tools:
            enhanced_prompt += """

[APPOINTMENT BOOKING - CRITICAL RULES]
You have tools to check calendar availability and book appointments. Follow these rules:

1. NEVER say "one moment", "let me check", "checking", or "I'll get back to you"
2. NEVER promise to do something without IMMEDIATELY calling the function
3. When the customer asks about times, call check_availability RIGHT NOW
4. When the customer picks a time, call book_appointment RIGHT NOW
5. EMAIL IS REQUIRED for booking - ask for it when offering time slots"""

        # Build session config - request TEXT output (we handle TTS)
        session_config: dict[str, Any] = {
            "instructions": enhanced_prompt,
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    }
                },
                # Still request audio output so Grok does STT properly
                # but we'll ignore the audio and use the transcript
                "output": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    }
                },
            },
            "turn_detection": {
                "type": self.agent.turn_detection_mode
                if self.agent and self.agent.turn_detection_mode
                else "server_vad",
                "threshold": 0.8,
                "prefix_padding_ms": 500,
                "silence_duration_ms": 1000,
            },
        }

        # Build tools list
        tools: list[dict[str, Any]] = []

        agent_enabled_tools = (
            self.agent.enabled_tools if self.agent and self.agent.enabled_tools else []
        )

        if "web_search" in agent_enabled_tools:
            tools.append(GROK_BUILTIN_TOOLS["web_search"])
            self.logger.info("grok_web_search_enabled")

        if "x_search" in agent_enabled_tools:
            tools.append(GROK_BUILTIN_TOOLS["x_search"])
            self.logger.info("grok_x_search_enabled")

        if self._enable_tools:
            tools.extend(VOICE_BOOKING_TOOLS)
            self.logger.info("booking_tools_enabled")

        if tools:
            session_config["tools"] = tools

        config = {
            "type": "session.update",
            "session": session_config,
        }

        await self._send_to_grok(config)
        self.logger.info("grok_session_configured_for_elevenlabs_tts")

    async def configure_session(
        self,
        voice: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        turn_detection_mode: str | None = None,
        turn_detection_threshold: float | None = None,
        silence_duration_ms: int | None = None,
    ) -> None:
        """Reconfigure the session.

        Note: Voice changes require reconnecting to ElevenLabs.
        For simplicity, voice is set at connection time based on agent config.
        """
        if not self.grok_ws:
            self.logger.warning("grok_not_connected")
            return

        session_config: dict[str, Any] = {}

        if system_prompt:
            # ALWAYS prepend date context first
            date_context = self._get_date_context()

            # Enhance prompt
            if self.agent and self.agent.name:
                agent_name = self.agent.name
                identity_prefix = (
                    f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
                    f"You MUST always identify yourself as {agent_name}.\n\n"
                )
                system_prompt = identity_prefix + system_prompt

            # Combine: date context (top) + system prompt
            enhanced = date_context + system_prompt
            enhanced = self._enhance_prompt_with_realism(enhanced)
            enhanced += self._get_search_tools_guidance()
            enhanced += "\n\nIMPORTANT: You are on a phone call. Speak naturally."
            session_config["instructions"] = enhanced

        if any([turn_detection_mode, turn_detection_threshold, silence_duration_ms]):
            turn_detection: dict[str, Any] = {
                "type": turn_detection_mode or "server_vad"
            }
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
            await self._send_to_grok(config)
            self.logger.info("session_reconfigured", updates=list(session_config.keys()))

    async def trigger_initial_response(self, greeting: str | None = None) -> None:
        """Trigger the AI to start speaking with an initial greeting.

        Args:
            greeting: Optional greeting text
        """
        if not self.grok_ws:
            self.logger.warning("grok_not_connected")
            return

        # Use provided greeting or agent's initial greeting
        message = greeting
        if not message and self.agent and self.agent.initial_greeting:
            message = self.agent.initial_greeting

        try:
            # Create user message prompting the AI to greet
            if message:
                prompt_text = f"Greet the caller by saying: {message}"
            else:
                prompt_parts = []
                if self.agent and self.agent.name:
                    prompt_parts.append(f"You are {self.agent.name}.")

                if hasattr(self, "_call_context") and self._call_context:
                    contact = self._call_context.get("contact", {})
                    offer = self._call_context.get("offer", {})

                    prompt_parts.append("This is an OUTBOUND call that YOU initiated.")

                    if contact and contact.get("name"):
                        prompt_parts.append(f"You are calling {contact['name']}.")

                    if offer and offer.get("name"):
                        prompt_parts.append(f"You are calling about: {offer['name']}.")

                    prompt_parts.append(
                        "Greet them, introduce yourself, and explain why you're calling."
                    )
                else:
                    prompt_parts.append(
                        "Greet the caller and introduce yourself briefly."
                    )

                prompt_text = " ".join(prompt_parts)

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

            await self._send_to_grok(event)
            await self._send_to_grok({"type": "response.create"})

            self.logger.info(
                "initial_response_triggered",
                has_greeting=bool(message),
            )

        except Exception as e:
            self.logger.exception("trigger_response_error", error=str(e))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send audio chunk to Grok for STT.

        Args:
            audio_data: PCM audio data (16-bit, 24kHz)
        """
        if not self.grok_ws:
            self.logger.warning("grok_not_connected")
            return

        try:
            encoded = base64.b64encode(audio_data).decode("utf-8")
            event = {
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }
            await self._send_to_grok(event)
        except Exception as e:
            self.logger.exception("send_audio_error", error=str(e))

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        """Stream audio responses from ElevenLabs TTS.

        Yields:
            ulaw_8000 audio chunks (ready for Telnyx, no conversion needed)
        """
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def _receive_from_grok(self) -> None:  # noqa: PLR0912, PLR0915
        """Receive events from Grok and route transcripts to ElevenLabs TTS."""
        if not self.grok_ws:
            return

        responses_completed = 0

        try:
            self.logger.info("starting_grok_receive_loop")

            async for message in self.grok_ws:
                try:
                    event = json.loads(message)
                except json.JSONDecodeError as e:
                    self.logger.warning("invalid_json_from_grok", error=str(e))
                    continue

                event_type = event.get("type", "")

                # Intercept audio transcript and send to ElevenLabs
                if event_type == "response.audio_transcript.delta":
                    transcript = event.get("delta", "")
                    # Send transcript to ElevenLabs for TTS
                    if (
                        transcript
                        and self._tts_session
                        and self._tts_session.is_connected()
                    ):
                        await self._tts_session.send_text(transcript, flush=True)
                        self.logger.debug(
                            "transcript_sent_to_elevenlabs",
                            text_preview=transcript[:30],
                        )

                # Ignore Grok's audio output - we use ElevenLabs TTS instead
                elif event_type in ("response.audio.delta", "response.output_audio.delta"):
                    # Explicitly ignoring Grok audio - ElevenLabs handles TTS
                    pass

                elif event_type == "response.done":
                    responses_completed += 1
                    response_data = event.get("response", {})
                    output_items = response_data.get("output", [])

                    # Handle function calls
                    for item in output_items:
                        if item.get("type") == "function_call":
                            await self._handle_function_call(item)

                    self.logger.info(
                        "grok_response_completed",
                        response_num=responses_completed,
                    )

                elif event_type == "response.output_item.done":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        await self._handle_function_call(item)

                elif event_type == "input_audio_buffer.speech_started":
                    self.logger.debug("user_speech_started")

                elif event_type == "input_audio_buffer.speech_stopped":
                    self.logger.debug("user_speech_stopped")

                elif event_type == "session.created":
                    session = event.get("session", {})
                    self.logger.info(
                        "grok_session_created",
                        session_id=session.get("id"),
                        model=session.get("model"),
                    )

                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(
                        "grok_error",
                        error_type=error.get("type"),
                        error_message=error.get("message"),
                    )

                else:
                    self.logger.debug("grok_event", event_type=event_type)

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "grok_connection_closed",
                code=e.code,
                reason=e.reason,
            )
        except asyncio.CancelledError:
            self.logger.info("grok_receive_cancelled")
        except Exception as e:
            self.logger.exception("grok_receive_error", error=str(e))

    async def _receive_from_tts(self) -> None:
        """Receive audio from ElevenLabs TTS and queue for output."""
        if not self._tts_session:
            return

        try:
            self.logger.info("starting_tts_receive_loop")
            async for audio_chunk in self._tts_session.receive_audio_stream():
                await self._audio_queue.put(audio_chunk)
        except asyncio.CancelledError:
            self.logger.info("tts_receive_cancelled")
        except Exception as e:
            self.logger.exception("tts_receive_error", error=str(e))

    async def _handle_function_call(self, item: dict[str, Any]) -> None:
        """Handle a function call from Grok."""
        call_id = item.get("call_id", "")
        function_name = item.get("name", "")
        arguments_str = item.get("arguments", "{}")

        self.logger.info(
            "function_call_received",
            call_id=call_id,
            function_name=function_name,
        )

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            arguments = {}

        if not self._tool_callback:
            self.logger.warning("no_tool_callback_set", function_name=function_name)
            await self.submit_tool_result(
                call_id,
                {"success": False, "error": "Tool execution not configured"},
            )
            return

        try:
            result = await self._tool_callback(call_id, function_name, arguments)
            self.logger.info(
                "function_call_executed",
                call_id=call_id,
                function_name=function_name,
                success=result.get("success", False) if isinstance(result, dict) else True,
            )
            await self.submit_tool_result(call_id, result)
        except Exception as e:
            self.logger.exception("function_call_error", error=str(e))
            await self.submit_tool_result(
                call_id,
                {"success": False, "error": str(e)},
            )

    async def submit_tool_result(
        self,
        call_id: str,
        result: dict[str, Any],
    ) -> None:
        """Submit tool execution result back to Grok."""
        if not self.grok_ws:
            return

        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result),
            },
        }

        try:
            await self._send_to_grok(event)
            await self._send_to_grok({"type": "response.create"})
            self.logger.info("tool_result_submitted", call_id=call_id)
        except Exception as e:
            self.logger.exception("submit_tool_result_error", error=str(e))

    async def inject_context(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
    ) -> None:
        """Inject conversation context."""
        if not self.grok_ws:
            return

        if not contact_info and not offer_info:
            return

        # Store context for trigger_initial_response
        self._call_context = {
            "contact": contact_info,
            "offer": offer_info,
        }

        # Build context section
        context_parts = [
            "\n\n# CURRENT CALL CONTEXT - THIS IS AN OUTBOUND CALL YOU ARE MAKING"
        ]

        if contact_info:
            context_parts.append("\n## Customer You Are Calling:")
            if contact_info.get("name"):
                context_parts.append(f"- Name: {contact_info['name']}")
            if contact_info.get("company"):
                context_parts.append(f"- Company: {contact_info['company']}")

        if offer_info:
            context_parts.append("\n## What You Are Calling About:")
            if offer_info.get("name"):
                context_parts.append(f"- Offer: {offer_info['name']}")
            if offer_info.get("description"):
                context_parts.append(f"- Details: {offer_info['description']}")

        context_section = "\n".join(context_parts)

        # ALWAYS start with date context - critical for appointment booking
        date_context = self._get_date_context()

        # Update session with context
        base_prompt = (
            self.agent.system_prompt
            if self.agent
            else "You are a helpful AI voice assistant."
        )

        if self.agent and self.agent.name:
            agent_name = self.agent.name
            identity_prefix = (
                f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
                f"You MUST always identify yourself as {agent_name}.\n\n"
            )
            base_prompt = identity_prefix + base_prompt

        # Combine: date context (top) + base prompt + call context
        full_prompt = date_context + base_prompt + context_section
        enhanced_prompt = self._enhance_prompt_with_realism(full_prompt)
        enhanced_prompt += "\n\nIMPORTANT: You are on a phone call that YOU initiated."

        config = {
            "type": "session.update",
            "session": {
                "instructions": enhanced_prompt,
            },
        }

        try:
            await self._send_to_grok(config)
            self.logger.info("context_injected")
        except Exception as e:
            self.logger.exception("inject_context_error", error=str(e))

    async def _send_to_grok(self, event: dict[str, Any]) -> None:
        """Send event to Grok WebSocket."""
        if not self.grok_ws:
            raise RuntimeError("Grok WebSocket not connected")

        try:
            await self.grok_ws.send(json.dumps(event))
        except Exception as e:
            self.logger.exception("send_to_grok_error", error=str(e))
            raise

    def is_connected(self) -> bool:
        """Check if both connections are active."""
        grok_connected = self.grok_ws is not None
        tts_connected = self._tts_session is not None and self._tts_session.is_connected()
        return grok_connected and tts_connected
