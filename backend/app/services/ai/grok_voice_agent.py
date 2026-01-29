"""Grok (xAI) Realtime API integration for voice conversations.

Grok Voice Agent API is compatible with OpenAI Realtime API format.
Supports realism enhancements via auditory cues: [whisper], [sigh], [laugh], etc.
Supports tool calling for Cal.com booking integration.
"""

import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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


class GrokVoiceAgentSession:
    """Grok (xAI) Realtime API session for voice conversations.

    Manages:
    - WebSocket connection to Grok Realtime API
    - Audio streaming and format conversion
    - Session configuration and context injection
    - Realism enhancements via auditory cues
    - Tool calling for Cal.com booking integration
    """

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
        self.api_key = api_key
        self.agent = agent
        self.ws: ClientConnection | None = None
        self.logger = logger.bind(service="grok_voice_agent")
        self._connection_task: asyncio.Task[None] | None = None
        self._enable_tools = enable_tools
        self._timezone = timezone

        # Tool call handling
        self._tool_callback: Callable[[str, str, dict[str, Any]], Any] | None = None
        self._pending_function_calls: dict[str, dict[str, Any]] = {}

        # Transcript tracking for debugging
        self._user_transcript: str = ""
        self._agent_transcript: str = ""
        self._transcript_entries: list[dict[str, Any]] = []

        # Interruption handling (barge-in)
        self._interruption_event: asyncio.Event | None = None

        # Response state tracking for proper interruption handling
        # When _is_interrupted is True, we skip yielding audio until response.done
        self._is_interrupted: bool = False

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

    def set_interruption_event(self, event: asyncio.Event) -> None:
        """Set event for signaling audio buffer clear on interruption.

        Args:
            event: asyncio.Event to set when user interrupts (barge-in)
        """
        self._interruption_event = event

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
        today_str = now.strftime("%A, %B %d, %Y")
        today_iso = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%I:%M %p")

        return (
            f"CRITICAL DATE CONTEXT: Today is {today_str} ({today_iso}). "
            f"The current time is {current_time}. "
            f"Your training data may be outdated - ALWAYS use {today_iso} as today's date.\n\n"
        )

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

    def _get_search_tools_guidance(self) -> str:
        """Get system prompt guidance for search tools.

        Returns:
            Search tools instructions if any search tools are enabled, empty string otherwise.
        """
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
                "facts you're unsure about, or anything that requires up-to-date information. "
                "Search results are integrated automatically - respond naturally."
            )

        if has_x_search:
            guidance_parts.append(
                "You have access to X (Twitter) search. "
                "Use it when users ask about trending topics, public opinions, "
                "what people are saying about something, or recent posts. "
                "The search results will help you provide current social context."
            )

        if has_web_search or has_x_search:
            guidance_parts.append(
                "Use these search tools proactively when the conversation would benefit "
                "from current information - don't wait to be asked explicitly."
            )

        return "\n".join(guidance_parts)

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
        # Build date context FIRST - this must be at the top of the prompt
        # so the model absolutely cannot ignore it
        date_context = self._get_date_context()

        # Get base prompt
        base_prompt = (
            self.agent.system_prompt
            if self.agent
            else "You are a helpful AI voice assistant."
        )

        # Prepend identity reinforcement if agent has a name configured
        if self.agent and self.agent.name:
            agent_name = self.agent.name
            identity_prefix = (
                f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
                f"You MUST always identify yourself as {agent_name}. "
                f"When greeting or introducing yourself, say your name is {agent_name}. "
                "This is non-negotiable.\n\n"
            )
            base_prompt = identity_prefix + base_prompt

        # Combine: date context (top) + base prompt
        enhanced_prompt = date_context + base_prompt

        # Enhance with realism cues
        enhanced_prompt = self._enhance_prompt_with_realism(enhanced_prompt)

        # Add search tools guidance if enabled
        enhanced_prompt += self._get_search_tools_guidance()

        # Add telephony-specific guidance to prevent hallucination at call start
        enhanced_prompt += """

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally and wait for response
- Do NOT generate random content, fun facts, or filler - stay focused on your purpose
- Speak clearly and conversationally as if on a real phone call"""

        # Add booking instructions when tools are enabled
        if self._enable_tools:
            # Get current date for booking context
            try:
                tz = ZoneInfo(self._timezone)
            except Exception:
                tz = ZoneInfo("America/New_York")
            now = datetime.now(tz)
            today_str = now.strftime("%A, %B %d, %Y")
            today_iso = now.strftime("%Y-%m-%d")

            enhanced_prompt += f"""

[APPOINTMENT BOOKING - CRITICAL DATE AND RULES]
TODAY IS {today_str} ({today_iso}).
Your training data may be outdated - IGNORE IT. The ACTUAL current date is {today_iso}.

When converting relative dates to YYYY-MM-DD format:
- "today" = {today_iso}
- "tomorrow" = the day after {today_iso}
- "Friday" = the NEXT Friday from {today_iso} (calculate it)
- "next week" = the week starting after {today_iso}
- "Monday" = the NEXT Monday from {today_iso}

You have tools to check calendar availability and book appointments. Follow these rules:

1. NEVER say "one moment", "let me check", "checking", or "I'll get back to you"
2. NEVER promise to do something without IMMEDIATELY calling the function
3. When the customer asks about times, call check_availability RIGHT NOW
4. When the customer picks a time, call book_appointment RIGHT NOW
5. EMAIL IS REQUIRED for booking - ask for it when offering time slots

WHEN TO CALL check_availability:
- Customer asks about availability ("when are you free", "what times work")
- Customer mentions a day ("Monday", "tomorrow", "next week", "Friday")
- Customer wants to schedule or book something
- ALWAYS use dates relative to {today_iso}, NOT your training data dates

WHEN TO CALL book_appointment:
- Customer confirms a specific time AND you have their email

RESPONSE PATTERN:
- If they ask about times: Call check_availability, then offer 2 specific options
- If they pick a time and you have email: Call book_appointment immediately
- If they pick a time but no email: Ask for email, then book once provided

DO NOT say things like "I'll check and get back to you" - you can check instantly!"""

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
        )
        if dtmf_enabled:
            tools.append(DTMF_TOOL)
            self.logger.info("grok_dtmf_tool_enabled")

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
            # ALWAYS prepend date context first - critical for appointment booking
            date_context = self._get_date_context()

            # Prepend identity reinforcement if agent has a name configured
            if self.agent and self.agent.name:
                agent_name = self.agent.name
                identity_prefix = (
                    f"CRITICAL IDENTITY INSTRUCTION: Your name is {agent_name}. "
                    f"You MUST always identify yourself as {agent_name}. "
                    f"When greeting or introducing yourself, say your name is {agent_name}. "
                    "This is non-negotiable.\n\n"
                )
                system_prompt = identity_prefix + system_prompt

            # Combine: date context (top) + system prompt
            enhanced = date_context + system_prompt

            # Enhance with realism cues, search guidance, and telephony guidance
            enhanced = self._enhance_prompt_with_realism(enhanced)
            enhanced += self._get_search_tools_guidance()
            enhanced += """

IMPORTANT: You are on a phone call. When the call connects:
- Wait briefly for the caller to speak first, OR
- If instructed to greet first, deliver your greeting naturally and wait for response
- Do NOT generate random content, fun facts, or filler - stay focused on your purpose
- Speak clearly and conversationally as if on a real phone call"""
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
            # Extract just the first name (before any | or - separator)
            full_name = self.agent.name if self.agent else "Jess"
            agent_name = full_name.split("|")[0].split("-")[0].strip().split()[0]
            # Pattern interrupt: honest, disarming, gives them a choice
            prompt_text = (
                f"You just called someone. Open with a pattern interrupt. "
                f"Say: 'Hey! It's {agent_name}. This is a sales call. "
                f"Do you wanna [sigh] hang up... or can I tell you why I'm calling?!' "
                f"Start friendly and upbeat. Sigh right before 'hang up' - sound disappointed. "
                f"Then get excited on 'or can I tell you why I'm calling?!' "
                f"Little laugh at the end. Wait for their response."
            )
        else:
            # For INBOUND calls: Use configured greeting or default
            message = greeting
            if not message and hasattr(self, "_pending_greeting"):
                message = self._pending_greeting
            if not message and self.agent and self.agent.initial_greeting:
                message = self.agent.initial_greeting

            if message:
                prompt_text = f"Greet the caller by saying: {message}"
            else:
                # Fallback for inbound calls without configured greeting
                prompt_parts = []

                if self.agent and self.agent.name:
                    prompt_parts.append(f"You are {self.agent.name}.")

                prompt_parts.append(
                    "Greet the caller and introduce yourself. Follow your "
                    "system instructions for the purpose of this call."
                )

                prompt_text = " ".join(prompt_parts)

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
                        self._agent_transcript += transcript
                        self.logger.info(
                            "grok_agent_transcript_delta",
                            delta=transcript,
                            full_transcript_so_far=self._agent_transcript[-200:],
                        )

                elif event_type == "response.text.delta":
                    # Alternative text transcript event
                    text = event.get("delta", "")
                    if text:
                        self._agent_transcript += text
                        self.logger.info(
                            "grok_agent_text_delta",
                            delta=text,
                        )

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    # User's speech transcript (what the human said)
                    user_text = event.get("transcript", "")
                    if user_text:
                        self._user_transcript = user_text
                        self._transcript_entries.append({
                            "role": "user",
                            "text": user_text,
                        })
                        self.logger.info(
                            "grok_user_transcript_completed",
                            user_said=user_text,
                        )

                elif event_type == "response.done":
                    # Response complete - but DON'T break!
                    # Keep listening for more responses in the conversation
                    responses_completed += 1

                    # Log the FULL response for debugging
                    response_data = event.get("response", {})
                    output_items = response_data.get("output", [])
                    response_status = response_data.get("status", "")

                    # Save agent transcript FIRST before handling cancellation
                    # This ensures partial transcripts are preserved even if
                    # interrupted (barge-in) or cancelled
                    if self._agent_transcript:
                        self._transcript_entries.append({
                            "role": "agent",
                            "text": self._agent_transcript,
                        })
                        self.logger.info(
                            "grok_agent_turn_completed",
                            agent_said=self._agent_transcript,
                        )
                        self._agent_transcript = ""

                    # If this was a cancelled response, clear interrupted flag
                    # This allows the next response to generate audio
                    if response_status == "cancelled" or self._is_interrupted:
                        self._is_interrupted = False
                        self.logger.info(
                            "grok_cancelled_response_complete",
                            status=response_status,
                        )

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
                    self.logger.info("grok_user_speech_started_interrupting")

                    # Set interrupted flag BEFORE cancel - blocks audio immediately
                    # This prevents audio chunks that arrive after cancel from being yielded
                    self._is_interrupted = True

                    # Cancel response - Grok will send response.done with status=cancelled
                    await self.cancel_response()

                    # Signal voice bridge to clear audio buffer immediately
                    if self._interruption_event:
                        self._interruption_event.set()

                elif event_type == "input_audio_buffer.speech_stopped":
                    self.logger.info("grok_user_speech_stopped")

                elif event_type == "response.created":
                    # New response starting - reset interrupted flag
                    # This is critical for outbound calls where the user speaks first:
                    # 1. User says "hello" -> speech_started -> _is_interrupted = True
                    # 2. User stops -> Grok generates response -> response.created
                    # 3. Without this reset, all audio would be skipped!
                    if self._is_interrupted:
                        self.logger.info(
                            "grok_resetting_interrupted_flag_on_new_response",
                            was_interrupted=True,
                        )
                        self._is_interrupted = False

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

        # Log full transcript at end of call
        self.logger.info(
            "grok_audio_stream_ended",
            total_chunks=audio_chunks_received,
            total_bytes=total_audio_bytes,
            total_responses=responses_completed,
            transcript_entry_count=len(self._transcript_entries),
        )

        # Log the full conversation transcript
        if self._transcript_entries:
            self.logger.info(
                "grok_full_conversation_transcript",
                transcript=json.dumps(self._transcript_entries, indent=2),
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

    async def inject_context(  # noqa: PLR0912
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

        # Build context section for system prompt
        context_parts = []

        if is_outbound:
            context_parts.append(
                "\n\n# CURRENT CALL CONTEXT - THIS IS AN OUTBOUND CALL YOU ARE MAKING"
            )
            context_parts.append(
                "You initiated this call. You know exactly why you're calling. "
                "Do NOT ask the customer what they want to talk about."
            )
        else:
            context_parts.append(
                "\n\n# CURRENT CALL CONTEXT - THIS IS AN INBOUND CALL"
            )
            context_parts.append(
                "The customer called you. Listen to what they need and assist them."
            )

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
            if offer_info.get("terms"):
                context_parts.append(f"- Terms: {offer_info['terms']}")

        context_section = "\n".join(context_parts)

        # Update session with context appended to instructions
        # ALWAYS start with date context - critical for appointment booking
        date_context = self._get_date_context()

        # Get current base prompt
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
                f"You MUST always identify yourself as {agent_name}. "
                f"When greeting or introducing yourself, say your name is {agent_name}. "
                "This is non-negotiable.\n\n"
            )
            base_prompt = identity_prefix + base_prompt

        # Combine: date context (top) + base prompt + call context
        full_prompt = date_context + base_prompt + context_section

        # Enhance with realism cues
        enhanced_prompt = self._enhance_prompt_with_realism(full_prompt)

        # Add telephony guidance based on call direction
        if is_outbound:
            enhanced_prompt += """

IMPORTANT: You are on a phone call that YOU initiated.
- You called THEM - introduce yourself and explain why you're calling
- Do NOT ask "what would you like to talk about" - YOU know why you called
- Be direct and professional about the purpose of your call"""
        else:
            enhanced_prompt += """

IMPORTANT: You are on a phone call. The customer called you.
- Listen to what they need and assist them appropriately
- Be helpful and responsive to their questions or concerns
- You may ask clarifying questions to understand their needs"""

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

    def get_transcript_json(self) -> str | None:
        """Get the conversation transcript as JSON string.

        Returns the transcript in a format suitable for storage and display:
        [{"role": "user", "text": "..."}, {"role": "agent", "text": "..."}]

        Returns:
            JSON string of transcript entries, or None if no transcript
        """
        if not self._transcript_entries:
            return None
        return json.dumps(self._transcript_entries)
