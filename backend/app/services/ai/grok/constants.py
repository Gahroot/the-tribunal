"""Grok voice agent constants and configuration.

This module contains Grok-specific configuration values:
- Voice configurations
- Realism enhancement cues
- Audio format settings
- Turn detection settings
- API configuration

Tool definitions (DTMF, booking, built-in tools) are in
app.services.ai.voice_tools to avoid duplication.
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
# Default silence duration is 3000ms to wait for complete IVR menus
IVR_TURN_DETECTION: dict[str, Any] = {
    "silence_duration_ms": 3000,
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
