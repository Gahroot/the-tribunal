"""Grok (xAI) Realtime API integration for voice conversations.

Grok Voice Agent API is compatible with OpenAI Realtime API format.
Supports realism enhancements via auditory cues: [whisper], [sigh], [laugh], etc.
Supports tool calling for Cal.com booking integration.
"""

import asyncio
import base64
import binascii
import json
import uuid as uuid_module
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog
import websockets

from app.models.agent import Agent
from app.services.ai.voice_agent_base import VoiceAgentBase

if TYPE_CHECKING:
    from app.services.ai.ivr_detector import IVRMode

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

# Grok built-in tools - these execute automatically, no callback needed
# Just include them in the session config and Grok handles the rest
GROK_BUILTIN_TOOLS = {
    "web_search": {
        "type": "web_search",
        # Grok's built-in web search - searches the internet for current information
    },
    "x_search": {
        "type": "x_search",
        # Grok's built-in X/Twitter search - searches posts on X
    },
}

# DTMF tool for IVR menu navigation
# Allows AI agent to send touch-tone digits during calls
DTMF_TOOL = {
    "type": "function",
    "name": "send_dtmf",
    "description": (
        "Send DTMF touch-tone digits during the call for IVR menu navigation. "
        "Use this when you hear an automated phone menu like 'Press 1 for sales, "
        "Press 2 for service'. Wait for the menu to finish speaking before sending. "
        "Common patterns: '0' or '#' often reaches an operator/human. "
        "Add 'w' between digits for 0.5s pause (e.g., '1w2' sends 1, waits, sends 2)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "digits": {
                "type": "string",
                "description": (
                    "DTMF digits to send. Valid: 0-9, *, #, A-D. "
                    "Use 'w' for 0.5s pause, 'W' for 1s pause between digits. "
                    "Examples: '1' (press 1), '0' (operator), '123#' (enter code), "
                    "'1w2w3' (digits with pauses for reliability)."
                ),
            },
        },
        "required": ["digits"],
    },
}

# Voice agent tool definitions for Cal.com booking
VOICE_BOOKING_TOOLS = [
    {
        "type": "function",
        "name": "book_appointment",
        "description": (
            "Book an appointment/meeting with the customer on Cal.com. "
            "Use this when the customer agrees to schedule a call, meeting, "
            "or appointment. You MUST collect the customer's email address first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Appointment date in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "Appointment time in HH:MM 24-hour format",
                },
                "email": {
                    "type": "string",
                    "description": "Customer's email address for booking confirmation",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes. Default is 30.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about the appointment",
                },
            },
            "required": ["date", "time", "email"],
        },
    },
    {
        "type": "function",
        "name": "check_availability",
        "description": (
            "Check available time slots on Cal.com for a date range. "
            "Use before booking to confirm slot availability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD (defaults to start)",
                },
            },
            "required": ["start_date"],
        },
    },
]


class GrokVoiceAgentSession(VoiceAgentBase):
    """Grok (xAI) Realtime API session for voice conversations.

    Manages:
    - WebSocket connection to Grok Realtime API
    - Audio streaming and format conversion
    - Session configuration and context injection
    - Realism enhancements via auditory cues
    - Tool calling for Cal.com booking integration

    Inherits from VoiceAgentBase for:
    - Transcript tracking
    - Interruption handling
    - Prompt building via VoicePromptBuilder
    """

    SERVICE_NAME = "grok_voice_agent"
    BASE_URL = "wss://api.x.ai/v1/realtime"

    def __init__(
        self,
        api_key: str,
        agent: Agent | None = None,
        enable_tools: bool = False,
        timezone: str = "America/New_York",
    ) -> None:
        """Initialize Grok voice agent session.

        Args:
            api_key: xAI API key
            agent: Optional Agent model for configuration
            enable_tools: Enable booking tools (requires Cal.com config)
            timezone: Timezone for date context (default: America/New_York)
        """
        super().__init__(agent, timezone)
        self.api_key = api_key
        self._connection_task: asyncio.Task[None] | None = None
        self._enable_tools = enable_tools

        # Tool call handling
        self._tool_callback: Callable[[str, str, dict[str, Any]], Any] | None = None
        self._pending_function_calls: dict[str, dict[str, Any]] = {}

        # Log initialization details
        self.logger.info(
            "grok_voice_agent_initialized",
            agent_name=agent.name if agent else None,
            agent_id=str(agent.id) if agent else None,
            enable_tools=enable_tools,
            calcom_event_type_id=agent.calcom_event_type_id if agent else None,
            enabled_tools=agent.enabled_tools if agent else None,
        )

    def set_tool_callback(
        self,
        callback: Callable[[str, str, dict[str, Any]], Any],
    ) -> None:
        """Set callback for tool execution.

        Args:
            callback: Async function(call_id, function_name, arguments) -> result
        """
        self._tool_callback = callback
        self.logger.info(
            "grok_tool_callback_set",
            callback_set=callback is not None,
            enable_tools=self._enable_tools,
        )

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
        await self._disconnect_ws()

    def _get_booking_tools(self) -> list[dict[str, Any]]:
        """Generate booking tools with current date context.

        Based on chatgpt-telegram-bot pattern of including current date
        in tool descriptions to help the model interpret relative dates.

        Returns:
            List of tool definitions with date context embedded
        """
        try:
            tz = ZoneInfo(self._timezone)
        except Exception:
            tz = ZoneInfo("America/New_York")

        now = datetime.now(tz)
        today_str = now.strftime("%A, %B %d, %Y")
        today_iso = now.strftime("%Y-%m-%d")

        return [
            {
                "type": "function",
                "name": "book_appointment",
                "description": (
                    f"Book an appointment on Cal.com. TODAY IS {today_str} ({today_iso}). "
                    f"When converting relative dates to YYYY-MM-DD: 'today' = {today_iso}, "
                    "'tomorrow' = the day after today, 'Friday' = the NEXT Friday from today. "
                    "You MUST collect the customer's email address first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": (
                                f"Appointment date in YYYY-MM-DD format. "
                                f"TODAY IS {today_iso}. Convert relative dates from this date."
                            ),
                        },
                        "time": {
                            "type": "string",
                            "description": "Appointment time in HH:MM 24-hour format",
                        },
                        "email": {
                            "type": "string",
                            "description": "Customer's email address for booking confirmation",
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Duration in minutes. Default is 30.",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional notes about the appointment",
                        },
                    },
                    "required": ["date", "time", "email"],
                },
            },
            {
                "type": "function",
                "name": "check_availability",
                "description": (
                    f"Check available time slots on Cal.com. "
                    f"TODAY IS {today_str} ({today_iso}). "
                    f"When the user says 'Friday', 'tomorrow', or 'next week', "
                    f"convert to YYYY-MM-DD relative to today ({today_iso}). "
                    f"Example: if today is {today_iso} and user says 'Friday', "
                    "calculate the next Friday from this date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": (
                                f"Start date in YYYY-MM-DD format. TODAY IS {today_iso}. "
                                "Convert relative dates like 'Friday' from this date."
                            ),
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD (defaults to start_date)",
                        },
                    },
                    "required": ["start_date"],
                },
            },
        ]

    async def _configure_session(self) -> None:  # noqa: PLR0915
        """Configure the Grok Realtime session with agent settings.

        Uses pcm16 at 24kHz - the voice_bridge handles conversion from/to
        Telnyx's μ-law 8kHz format.
        """
        # Build full prompt using the prompt builder
        enhanced_prompt = self._prompt_builder.build_full_prompt(
            include_realism=True,
            include_booking=self._enable_tools,
        )

        # Get voice - default to 'Ara' for Grok (capitalized)
        voice = "Ara"
        if self.agent and self.agent.voice_id:
            voice_lower = self.agent.voice_id.lower()
            # Validate voice
            if voice_lower not in GROK_VOICES:
                self.logger.warning(
                    "invalid_grok_voice",
                    voice=voice_lower,
                    defaulting_to="Ara",
                )
            else:
                # Grok expects capitalized voice names
                voice = voice_lower.capitalize()

        # Log the full instructions being sent for debugging
        self.logger.info(
            "grok_configuring_session",
            voice=voice,
            instructions_length=len(enhanced_prompt),
            instructions_preview=enhanced_prompt[:200],
        )

        session_config: dict[str, Any] = {
            "instructions": enhanced_prompt,
            "voice": voice,
            # Grok audio format (different from OpenAI)
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    }
                },
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
                # Lower threshold = more sensitive to speech detection
                "threshold": 0.5,
                # More padding before speech starts (captures audio before VAD triggers)
                "prefix_padding_ms": 800,
                # Wait for silence before responding
                "silence_duration_ms": 700,
            },
        }

        # Build tools list from agent's enabled_tools
        tools: list[dict[str, Any]] = []

        # Add Grok built-in tools if enabled in agent settings
        agent_enabled_tools = (
            self.agent.enabled_tools if self.agent and self.agent.enabled_tools else []
        )

        if "web_search" in agent_enabled_tools:
            tools.append(GROK_BUILTIN_TOOLS["web_search"])
            self.logger.info("grok_web_search_enabled")

        if "x_search" in agent_enabled_tools:
            tools.append(GROK_BUILTIN_TOOLS["x_search"])
            self.logger.info("grok_x_search_enabled")

        # Add DTMF tool for IVR navigation if enabled
        # Check both patterns: direct tool ID in enabled_tools (legacy)
        # or integration-based: "call_control" in enabled_tools + "send_dtmf" in tool_settings
        # Also auto-enable if IVR detector is active (for outbound calls)
        tool_settings = (
            self.agent.tool_settings if self.agent and self.agent.tool_settings else {}
        )
        call_control_tools = tool_settings.get("call_control", []) or []
        dtmf_enabled = (
            "send_dtmf" in agent_enabled_tools  # Legacy/direct pattern
            or (
                "call_control" in agent_enabled_tools
                and "send_dtmf" in call_control_tools
            )  # Integration-based pattern
            or self._ivr_detector is not None  # Auto-enable if IVR detection active
        )
        if dtmf_enabled:
            tools.append(DTMF_TOOL)
            dtmf_reason = (
                "ivr_detector_active"
                if self._ivr_detector is not None
                else "explicit_config"
            )
            self.logger.info("grok_dtmf_tool_enabled", reason=dtmf_reason)

        # Add Cal.com booking tools if enabled and configured
        # Use dynamic tools with current date context embedded
        if self._enable_tools:
            booking_tools = self._get_booking_tools()
            tools.extend(booking_tools)
            self.logger.info(
                "grok_booking_tools_enabled",
                tool_count=len(booking_tools),
            )

        if tools:
            session_config["tools"] = tools
            tool_names = [
                t.get("name", t.get("type", "unknown")) for t in tools
            ]
            self.logger.info(
                "grok_tools_configured",
                total_tool_count=len(tools),
                tool_names=tool_names,
                tools_json=json.dumps(tools, indent=2),
            )
        else:
            self.logger.warning(
                "grok_no_tools_configured",
                enable_tools=self._enable_tools,
                agent_enabled_tools=agent_enabled_tools,
            )

        config: dict[str, Any] = {
            "type": "session.update",
            "session": session_config,
        }

        # Log the full session config being sent
        self.logger.info(
            "grok_sending_session_update",
            session_config_keys=list(session_config.keys()),
            has_tools="tools" in session_config,
            tool_count=len(session_config.get("tools", [])),
        )

        await self._send_event(config)
        self.logger.info(
            "grok_session_configured",
            voice=voice,
            audio_format="pcm16",
            tools_enabled=self._enable_tools,
            tool_callback_set=self._tool_callback is not None,
        )

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
            temperature: Response temperature (may not be supported by Grok)
            turn_detection_mode: Turn detection type (server_vad)
            turn_detection_threshold: VAD threshold (0.0-1.0)
            silence_duration_ms: Silence duration before turn ends
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        session_config: dict[str, Any] = {}

        if voice:
            # Validate and normalize voice - Grok uses capitalized names
            voice_lower = voice.lower()
            if voice_lower in GROK_VOICES:
                # Grok expects capitalized voice names like "Ara", "Rex"
                session_config["voice"] = voice_lower.capitalize()
            else:
                self.logger.warning("invalid_grok_voice", voice=voice)

        if system_prompt:
            # Build enhanced prompt using prompt builder
            enhanced = self._prompt_builder.build_full_prompt(
                base_prompt=system_prompt,
                include_realism=True,
                include_booking=self._enable_tools,
            )
            session_config["instructions"] = enhanced

        # Configure turn detection
        if any([turn_detection_mode, turn_detection_threshold, silence_duration_ms]):
            turn_detection: dict[str, Any] = {
                "type": turn_detection_mode or "server_vad"
            }
            if turn_detection_threshold is not None:
                turn_detection["threshold"] = turn_detection_threshold
            if silence_duration_ms is not None:
                turn_detection["silence_duration_ms"] = silence_duration_ms
            turn_detection["prefix_padding_ms"] = 800
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

        # Store the greeting for later use by trigger_initial_response
        self._pending_greeting = greeting

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

    async def trigger_initial_response(
        self,
        greeting: str | None = None,
        is_outbound: bool = False,
    ) -> None:
        """Trigger the AI to start speaking with the initial greeting.

        Call this after the audio stream is established to initiate the conversation.
        Creates a user message prompting the AI to greet, then triggers response.create().

        For OUTBOUND calls, we do NOT trigger a greeting - we wait for the person
        to say "hello" first, then the AI responds naturally using the context
        already injected via inject_context().

        Args:
            greeting: Optional greeting text. If not provided, uses the pending greeting
                     from send_greeting or agent's initial greeting.
            is_outbound: If True, this is an outbound call and we should NOT greet first.
                        The AI will wait for the person to speak, then respond.
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        # For OUTBOUND calls: Use a pattern interrupt opener
        # Be honest and disarming - give them control
        if is_outbound:
            self.logger.info(
                "grok_outbound_call_pattern_interrupt",
                is_outbound=True,
                has_call_context=hasattr(self, "_call_context") and bool(self._call_context),
            )
            # Use prompt builder but add Grok-specific realism cues
            base_prompt = self._prompt_builder.get_outbound_opener_prompt()
            # Add Grok realism cues to the pattern interrupt
            prompt_text = base_prompt.replace(
                "Sound a bit disappointed on 'hang up'.",
                "Sigh right before 'hang up' - sound disappointed.",
            ) + " Little laugh at the end."
        else:
            # For INBOUND calls: Use configured greeting or default
            message = greeting
            if not message and hasattr(self, "_pending_greeting"):
                message = self._pending_greeting
            if not message and self.agent and self.agent.initial_greeting:
                message = self.agent.initial_greeting

            prompt_text = self._prompt_builder.get_inbound_greeting_prompt(message)

        # Send the greeting/opener for both inbound and outbound
        try:
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
                "grok_initial_response_triggered",
                prompt_length=len(prompt_text),
                is_outbound=is_outbound,
            )

            # Trigger response generation
            await self._send_event({"type": "response.create"})
            self.logger.info("grok_response_requested", is_outbound=is_outbound)

        except Exception as e:
            self.logger.exception("grok_trigger_response_error", error=str(e))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send audio chunk to Grok.

        Args:
            audio_data: PCM audio data (16-bit, 16kHz)
        """
        await self._send_audio_base64(audio_data)

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:  # noqa: PLR0912, PLR0915
        """Stream audio responses from Grok.

        This generator continuously yields audio chunks from the Grok Realtime API.
        It does NOT break on response.done - instead it keeps listening for more
        responses as the conversation continues.

        Yields:
            PCM audio chunks (16-bit, 16kHz)
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected_for_audio_stream")
            return

        audio_chunks_received = 0
        total_audio_bytes = 0
        responses_completed = 0

        try:
            self.logger.info("grok_starting_audio_receive_stream")

            async for message in self.ws:
                # Parse JSON with error handling to prevent stream crash
                try:
                    event = json.loads(message)
                except json.JSONDecodeError as e:
                    self.logger.warning(
                        "invalid_json_from_grok",
                        error=str(e),
                        message_preview=str(message)[:100],
                    )
                    continue

                event_type = event.get("type", "")

                # Log ALL events for debugging (except high-frequency audio deltas)
                if event_type not in ("response.audio.delta", "response.output_audio.delta"):
                    if event_type == "session.created":
                        event_preview = "..."
                    else:
                        event_preview = json.dumps(event)[:500]
                    self.logger.info(
                        "grok_event_received",
                        event_type=event_type,
                        event_keys=list(event.keys()),
                        event_preview=event_preview,
                    )

                # Grok uses same event types as OpenAI Realtime
                if event_type == "response.audio.delta":
                    # Skip audio if we're in interrupted state (barge-in handling)
                    # Grok continues sending audio for 100-500ms after cancel
                    if self._is_interrupted:
                        continue

                    audio_data = event.get("delta", "")
                    if audio_data:
                        # Decode base64 with error handling
                        try:
                            decoded = base64.b64decode(audio_data)
                        except (binascii.Error, ValueError) as e:
                            self.logger.warning(
                                "invalid_base64_audio_from_grok",
                                error=str(e),
                            )
                            continue

                        audio_chunks_received += 1
                        total_audio_bytes += len(decoded)

                        if audio_chunks_received % 100 == 0:
                            self.logger.debug(
                                "grok_audio_stream_progress",
                                chunks=audio_chunks_received,
                                total_bytes=total_audio_bytes,
                                responses=responses_completed,
                            )

                        yield decoded

                elif event_type == "response.output_audio.delta":
                    # Alternative event name in Grok API
                    # Skip audio if we're in interrupted state (barge-in handling)
                    if self._is_interrupted:
                        continue

                    audio_data = event.get("delta", "")
                    if audio_data:
                        # Decode base64 with error handling
                        try:
                            decoded = base64.b64decode(audio_data)
                        except (binascii.Error, ValueError) as e:
                            self.logger.warning(
                                "invalid_base64_audio_from_grok",
                                error=str(e),
                            )
                            continue

                        audio_chunks_received += 1
                        total_audio_bytes += len(decoded)
                        yield decoded

                elif event_type == "response.audio_transcript.delta":
                    # Agent's speech transcript (what the AI is saying)
                    transcript = event.get("delta", "")
                    if transcript:
                        self._append_agent_transcript_delta(transcript)
                        self.logger.info(
                            "grok_agent_transcript_delta",
                            delta=transcript,
                            full_transcript_so_far=self._agent_transcript[-200:],
                        )

                        # ALWAYS check for DTMF tags - primary mechanism for IVR navigation
                        # This works regardless of whether function calling is supported
                        await self._check_and_send_dtmf_tags(self._agent_transcript)

                        # Also process through IVR detector if enabled
                        if self._ivr_detector:
                            await self.process_ivr_transcript(
                                self._agent_transcript, is_agent=True
                            )

                elif event_type == "response.output_audio_transcript.delta":
                    # Alternative transcript event format from Grok API
                    transcript = event.get("delta", "")
                    if transcript:
                        self._append_agent_transcript_delta(transcript)
                        self.logger.info(
                            "grok_agent_output_transcript_delta",
                            delta=transcript,
                            full_transcript_so_far=self._agent_transcript[-200:],
                        )

                        # ALWAYS check for DTMF tags - primary mechanism for IVR navigation
                        await self._check_and_send_dtmf_tags(self._agent_transcript)

                        # Also process through IVR detector if enabled
                        if self._ivr_detector:
                            await self.process_ivr_transcript(
                                self._agent_transcript, is_agent=True
                            )

                elif event_type == "response.text.delta":
                    # Alternative text transcript event
                    text = event.get("delta", "")
                    if text:
                        self._append_agent_transcript_delta(text)
                        self.logger.info(
                            "grok_agent_text_delta",
                            delta=text,
                        )

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    # User's speech transcript (what the human said)
                    user_text = event.get("transcript", "")
                    if user_text:
                        self._add_user_transcript(user_text)

                        # Process through IVR detector if enabled
                        if self._ivr_detector:
                            old_mode = self._ivr_mode
                            new_mode = await self.process_ivr_transcript(
                                user_text, is_agent=False
                            )
                            if new_mode != old_mode:
                                await self._handle_ivr_mode_switch(old_mode, new_mode)

                elif event_type == "response.done":
                    # Response complete - but DON'T break!
                    # Keep listening for more responses in the conversation
                    responses_completed += 1

                    # Log the FULL response for debugging
                    response_data = event.get("response", {})
                    output_items = response_data.get("output", [])
                    response_status = response_data.get("status", "")

                    # Handle response completion using base class
                    self._handle_response_done(response_status)

                    # Log complete response structure
                    self.logger.info(
                        "grok_response_done_full",
                        response_id=response_data.get("id"),
                        response_status=response_data.get("status"),
                        output_item_count=len(output_items),
                        output_item_types=[item.get("type") for item in output_items],
                        full_response=json.dumps(response_data)[:2000],
                    )

                    # Check for function calls in the response
                    function_calls_found = 0
                    for item in output_items:
                        item_type = item.get("type")
                        self.logger.info(
                            "grok_response_output_item",
                            item_type=item_type,
                            item_keys=list(item.keys()),
                            item_preview=json.dumps(item)[:500],
                        )
                        if item_type == "function_call":
                            function_calls_found += 1
                            self.logger.info(
                                "grok_function_call_found_in_response",
                                function_name=item.get("name"),
                                call_id=item.get("call_id"),
                                arguments=item.get("arguments"),
                            )
                            await self._handle_function_call(item)

                    self.logger.info(
                        "grok_response_completed",
                        response_num=responses_completed,
                        total_audio_chunks=audio_chunks_received,
                        total_audio_bytes=total_audio_bytes,
                        function_calls_found=function_calls_found,
                        tool_callback_set=self._tool_callback is not None,
                    )
                    # Continue listening for next response

                elif event_type == "response.output_item.done":
                    # Handle completed output items (including function calls)
                    item = event.get("item", {})
                    item_type = item.get("type")
                    self.logger.info(
                        "grok_output_item_done",
                        item_type=item_type,
                        item_keys=list(item.keys()),
                        item_preview=json.dumps(item)[:500],
                    )
                    if item_type == "function_call":
                        self.logger.info(
                            "grok_function_call_in_output_item_done",
                            function_name=item.get("name"),
                            call_id=item.get("call_id"),
                        )
                        await self._handle_function_call(item)

                elif event_type == "input_audio_buffer.speech_started":
                    # Handle barge-in using base class helper
                    self._handle_speech_started()

                    # Cancel response - Grok will send response.done with status=cancelled
                    await self.cancel_response()

                elif event_type == "input_audio_buffer.speech_stopped":
                    self.logger.info("grok_user_speech_stopped")

                elif event_type == "response.created":
                    # Handle new response - resets interrupted flag using base class
                    self._handle_response_created()

                elif event_type == "session.created":
                    session = event.get("session", {})
                    session_tools = session.get("tools", [])
                    self.logger.info(
                        "grok_session_created",
                        session_id=session.get("id"),
                        model=session.get("model"),
                        voice=session.get("voice"),
                        tools_in_session=[t.get("name", t.get("type")) for t in session_tools],
                        tool_count=len(session_tools),
                        full_session_config=json.dumps(session)[:1000],
                    )

                elif event_type == "session.updated":
                    session = event.get("session", {})
                    session_tools = session.get("tools", [])
                    self.logger.info(
                        "grok_session_updated",
                        session_id=session.get("id"),
                        tools_in_session=[t.get("name", t.get("type")) for t in session_tools],
                        tool_count=len(session_tools),
                    )

                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(
                        "grok_realtime_error",
                        error_type=error.get("type"),
                        error_message=error.get("message"),
                        error_code=error.get("code"),
                        full_error=json.dumps(event),
                    )
                    # Don't break - some errors are recoverable

                elif event_type in (
                    "response.output_item.added",
                    "conversation.item.added",
                    "response.content_part.added",
                    "response.content_part.done",
                ):
                    # Informational events - log at debug level
                    self.logger.debug(
                        "grok_informational_event",
                        event_type=event_type,
                    )

                else:
                    # Log unknown events at info level for debugging
                    self.logger.info(
                        "grok_unknown_event",
                        event_type=event_type,
                        event_keys=list(event.keys()),
                    )

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "grok_websocket_closed",
                code=e.code,
                reason=e.reason,
                chunks_received=audio_chunks_received,
            )
        except Exception as e:
            self.logger.exception(
                "grok_receive_audio_stream_error",
                error=str(e),
                chunks_received=audio_chunks_received,
            )

        # Log stream end stats
        self.logger.info(
            "grok_audio_stream_ended",
            total_chunks=audio_chunks_received,
            total_bytes=total_audio_bytes,
            total_responses=responses_completed,
            transcript_entry_count=len(self._transcript_entries),
        )

    async def _handle_function_call(self, item: dict[str, Any]) -> None:
        """Handle a function call from Grok.

        Executes the tool callback and sends the result back to Grok.

        Args:
            item: Function call item from Grok response
        """
        call_id = item.get("call_id", "")
        function_name = item.get("name", "")
        arguments_str = item.get("arguments", "{}")

        self.logger.info(
            "grok_function_call_received",
            call_id=call_id,
            function_name=function_name,
            arguments=arguments_str[:100],
        )

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            arguments = {}
            self.logger.warning(
                "grok_function_call_invalid_arguments",
                arguments=arguments_str,
            )

        if not self._tool_callback:
            self.logger.warning(
                "grok_no_tool_callback_set",
                function_name=function_name,
            )
            # Send error result back
            await self.submit_tool_result(
                call_id,
                {"success": False, "error": "Tool execution not configured"},
            )
            return

        # Timeout for tool execution to prevent blocking audio stream
        tool_timeout_seconds = 10.0

        try:
            # Execute the tool callback with timeout protection
            result = await asyncio.wait_for(
                self._tool_callback(call_id, function_name, arguments),
                timeout=tool_timeout_seconds,
            )

            self.logger.info(
                "grok_function_call_executed",
                call_id=call_id,
                function_name=function_name,
                success=result.get("success", False) if isinstance(result, dict) else True,
            )

            # Send result back to Grok
            await self.submit_tool_result(call_id, result)

        except TimeoutError:
            self.logger.error(
                "grok_function_call_timeout",
                call_id=call_id,
                function_name=function_name,
                timeout_seconds=tool_timeout_seconds,
            )
            await self.submit_tool_result(
                call_id,
                {"success": False, "error": "Tool execution timed out. Please try again."},
            )

        except Exception as e:
            self.logger.exception(
                "grok_function_call_error",
                call_id=call_id,
                function_name=function_name,
                error=str(e),
            )
            await self.submit_tool_result(
                call_id,
                {"success": False, "error": str(e)},
            )

    async def submit_tool_result(
        self,
        call_id: str,
        result: dict[str, Any],
    ) -> None:
        """Submit tool execution result back to Grok.

        Args:
            call_id: The function call ID from Grok
            result: The result to send back
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        # Create conversation item with tool result
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result),
            },
        }

        try:
            await self._send_event(event)
            self.logger.info(
                "grok_tool_result_submitted",
                call_id=call_id,
            )

            # Trigger Grok to continue the conversation with the result
            await self._send_event({"type": "response.create"})

        except Exception as e:
            self.logger.exception(
                "grok_submit_tool_result_error",
                call_id=call_id,
                error=str(e),
            )

    async def cancel_response(self) -> None:
        """Cancel the current response generation (barge-in handling).

        This is called when the user starts speaking during AI response
        to immediately stop Grok's audio generation. Production pattern
        from VideoSDK/LiveKit/OpenAI clients.
        """
        if not self.ws:
            return
        try:
            await self._send_event({"type": "response.cancel"})
            self.logger.info("grok_response_cancelled_on_interruption")
        except Exception as e:
            self.logger.exception("grok_cancel_response_error", error=str(e))

    async def inject_context(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
        is_outbound: bool = True,
    ) -> None:
        """Inject conversation context by updating system instructions.

        This updates the session instructions to include contact and offer
        context, rather than injecting as user messages which confuses the AI.

        Args:
            contact_info: Contact information (name, company, etc.)
            offer_info: Offer/product information
            is_outbound: True if this is an outbound call, False for inbound
        """
        if not self.ws:
            self.logger.warning("grok_websocket_not_connected")
            return

        if not contact_info and not offer_info:
            return

        # Store context for use in trigger_initial_response
        self._call_context = {
            "contact": contact_info,
            "offer": offer_info,
        }

        # Build full instructions using prompt builder
        enhanced_prompt = self._prompt_builder.build_full_prompt(
            include_realism=True,
            include_booking=self._enable_tools,
            contact_info=contact_info,
            offer_info=offer_info,
            is_outbound=is_outbound,
        )

        # Send session update with full context
        config = {
            "type": "session.update",
            "session": {
                "instructions": enhanced_prompt,
            },
        }

        try:
            await self._send_event(config)
            self.logger.info("grok_context_injected_to_instructions")
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

    # -------------------------------------------------------------------------
    # IVR Detection Overrides
    # -------------------------------------------------------------------------

    async def _handle_ivr_mode_switch(
        self,
        old_mode: "IVRMode",
        new_mode: "IVRMode",
    ) -> None:
        """Handle IVR mode switching with Grok-specific behavior.

        Args:
            old_mode: Previous IVR mode
            new_mode: New IVR mode
        """
        from app.services.ai.ivr_detector import IVRMode

        self.logger.info(
            "grok_ivr_mode_switch",
            old_mode=old_mode.value,
            new_mode=new_mode.value,
        )

        if new_mode == IVRMode.IVR:
            await self._switch_to_ivr_mode()
        elif new_mode == IVRMode.CONVERSATION:
            await self._switch_to_conversation_mode()
        elif new_mode == IVRMode.VOICEMAIL:
            await self._switch_to_voicemail_mode()

    async def _switch_to_ivr_mode(self) -> None:
        """Switch to IVR navigation mode.

        Adjusts turn detection for IVR menus which often have longer pauses.
        """
        self.logger.info("grok_switching_to_ivr_mode")

        # Increase silence duration for IVR menus
        # IVR systems have longer pauses between options
        await self.configure_session(
            silence_duration_ms=1500,  # Longer pause for IVR menus
            turn_detection_threshold=0.6,  # Less sensitive
        )

        # Update prompt to include IVR navigation guidance
        if self._ivr_detector and self._ivr_navigation_goal:
            ivr_prompt = self._ivr_detector.get_ivr_navigation_prompt(
                self._ivr_navigation_goal
            )
            # Inject IVR navigation context
            await self._inject_ivr_context(ivr_prompt)

    async def _switch_to_conversation_mode(self) -> None:
        """Switch back to normal conversation mode.

        Restores normal turn detection settings.
        """
        self.logger.info("grok_switching_to_conversation_mode")

        # Restore normal settings
        silence_ms = 700
        threshold = 0.5

        if self.agent:
            silence_ms = self.agent.silence_duration_ms or 700
            threshold = self.agent.turn_detection_threshold or 0.5

        await self.configure_session(
            silence_duration_ms=silence_ms,
            turn_detection_threshold=threshold,
        )

    async def _switch_to_voicemail_mode(self) -> None:
        """Switch to voicemail handling mode.

        Similar to IVR mode but with voicemail-specific guidance.
        """
        self.logger.info("grok_switching_to_voicemail_mode")

        # Voicemail systems often have beeps and long pauses
        await self.configure_session(
            silence_duration_ms=2000,  # Wait for beep
            turn_detection_threshold=0.7,  # Less sensitive during recording prompt
        )

    async def _inject_ivr_context(self, ivr_prompt: str) -> None:
        """Inject IVR navigation context into session.

        Args:
            ivr_prompt: IVR navigation prompt to inject
        """
        if not self.ws:
            return

        # Create a user message with IVR instructions
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"[SYSTEM IVR NAVIGATION] {ivr_prompt}",
                    }
                ],
            },
        }

        try:
            await self._send_event(event)
            self.logger.info("grok_ivr_context_injected")
        except Exception as e:
            self.logger.exception("grok_ivr_context_inject_error", error=str(e))

    def _handle_ivr_dtmf(self, digits: str) -> None:
        """Handle DTMF digits detected in agent response.

        Calls the tool callback to send DTMF via telephony provider.

        Args:
            digits: DTMF digits to send (0-9, *, #, A-D)
        """
        self.logger.info("grok_ivr_dtmf_auto_send", digits=digits)

        # Send DTMF via tool callback if available
        if self._tool_callback:
            import asyncio

            # Schedule DTMF send via tool callback
            # The callback is async but this method is sync
            asyncio.create_task(
                self._send_dtmf_via_callback(digits)
            )

    async def _send_dtmf_via_callback(self, digits: str) -> None:
        """Send DTMF via tool callback.

        Args:
            digits: DTMF digits to send
        """
        if not self._tool_callback:
            self.logger.warning("no_tool_callback_for_dtmf")
            return

        try:
            # Generate a unique call ID for this DTMF send
            call_id = f"dtmf_{uuid_module.uuid4().hex[:8]}"

            result = await self._tool_callback(
                call_id,
                "send_dtmf",
                {"digits": digits},
            )

            self.logger.info(
                "grok_dtmf_sent_via_callback",
                digits=digits,
                result=result,
            )
        except Exception as e:
            self.logger.exception(
                "grok_dtmf_send_error",
                digits=digits,
                error=str(e),
            )
            raise

    async def _check_and_send_dtmf_tags(self, text: str) -> None:
        """Check for DTMF tags in text and send them.

        This is the PRIMARY mechanism for DTMF detection since xAI function
        calling may not work reliably. Parses <dtmf>X</dtmf> tags from agent
        transcript and sends the digits via the tool callback.

        Args:
            text: Text to check for DTMF tags
        """
        import re

        from app.services.ai.ivr_detector import DTMFContext, DTMFValidator

        # Track which DTMF sequences we've already sent to avoid duplicates
        if not hasattr(self, "_sent_dtmf_sequences"):
            self._sent_dtmf_sequences: set[str] = set()

        pattern = re.compile(r"<dtmf>([0-9*#A-Dw]+)</dtmf>", re.IGNORECASE)
        matches = pattern.findall(text)

        for digits in matches:
            # Create a unique key for this specific occurrence
            # Use position in text to allow same digits to be sent multiple times
            # if they appear at different positions
            occurrence_key = f"{text.find(f'<dtmf>{digits}</dtmf>')}:{digits}"
            if occurrence_key in self._sent_dtmf_sequences:
                continue

            # Filter to only valid DTMF characters
            valid_chars = set("0123456789*#ABCDabcd")
            actual_digits = "".join(c for c in digits if c in valid_chars)

            if actual_digits:
                # Get current IVR context
                ivr_status = self.get_ivr_status()
                context = DTMFContext.MENU  # Default
                if ivr_status and hasattr(ivr_status, "menu_state") and ivr_status.menu_state:
                    context = ivr_status.menu_state.context

                # Split digits based on context (fixes multi-digit bug)
                validator = DTMFValidator()
                digit_sequences = validator.split_dtmf_by_context(actual_digits, context)

                self.logger.info(
                    "dtmf_tag_detected_with_context",
                    raw_digits=digits,
                    context=context.value if hasattr(context, "value") else str(context),
                    will_send_as=digit_sequences,
                )

                # Send each sequence separately with delay
                self._sent_dtmf_sequences.add(occurrence_key)
                for seq in digit_sequences:
                    await self._send_dtmf_via_callback(seq)
                    if self._ivr_detector:
                        self._ivr_detector.record_dtmf_attempt(seq)
                    if len(digit_sequences) > 1:
                        await asyncio.sleep(0.3)  # Delay between presses

