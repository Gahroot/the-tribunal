"""Grok voice agent constants and tool definitions.

This module contains all static configuration values for the Grok voice agent:
- Voice configurations
- Realism enhancement cues
- Built-in tool definitions (web_search, x_search)
- DTMF tool for IVR navigation
- Cal.com booking tool schemas
"""

from typing import Any

# Grok available voices
GROK_VOICES: dict[str, str] = {
    "ara": "Ara - Warm & friendly (female, default)",
    "rex": "Rex - Confident & clear (male)",
    "sal": "Sal - Smooth & balanced (neutral)",
    "eve": "Eve - Energetic & upbeat (female)",
    "leo": "Leo - Authoritative & strong (male)",
}

# Default voice for Grok (capitalized as Grok expects)
DEFAULT_VOICE = "Ara"

# Realism enhancement cues that can be used in prompts
GROK_REALISM_CUES: list[str] = [
    "[whisper]",
    "[sigh]",
    "[laugh]",
    "[pause]",
    "[breath]",
]

# Grok built-in tools - these execute automatically, no callback needed
# Just include them in the session config and Grok handles the rest
GROK_BUILTIN_TOOLS: dict[str, dict[str, str]] = {
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
DTMF_TOOL: dict[str, Any] = {
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

# Voice agent tool definitions for Cal.com booking (static schema)
# Note: Use get_booking_tools_with_date_context() for tools with current date
VOICE_BOOKING_TOOLS: list[dict[str, Any]] = [
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

# Audio configuration for Grok Realtime API
AUDIO_CONFIG: dict[str, dict[str, dict[str, str | int]]] = {
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
}

# Default turn detection settings
DEFAULT_TURN_DETECTION: dict[str, Any] = {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 800,
    "silence_duration_ms": 700,
}

# IVR mode turn detection settings
IVR_TURN_DETECTION: dict[str, Any] = {
    "silence_duration_ms": 1500,
    "turn_detection_threshold": 0.6,
}

# Voicemail mode turn detection settings
VOICEMAIL_TURN_DETECTION: dict[str, Any] = {
    "silence_duration_ms": 2000,
    "turn_detection_threshold": 0.7,
}

# Tool execution timeout in seconds
TOOL_TIMEOUT_SECONDS: float = 10.0

# Grok Realtime API base URL
GROK_REALTIME_BASE_URL = "wss://api.x.ai/v1/realtime"
