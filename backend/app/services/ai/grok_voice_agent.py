"""Grok (xAI) Realtime API integration for voice conversations.

This module provides backward compatibility for imports from the original location.
The implementation has been refactored into the grok/ package.

For new code, import directly from:
    from app.services.ai.grok import GrokVoiceAgentSession

Or use the constants from:
    from app.services.ai.grok.constants import GROK_VOICES, DTMF_TOOL, etc.
"""

# Re-export from refactored package for backward compatibility
from app.services.ai.grok import GrokVoiceAgentSession
from app.services.ai.grok.constants import (
    DTMF_TOOL,
    GROK_BUILTIN_TOOLS,
    GROK_REALISM_CUES,
    GROK_VOICES,
    VOICE_BOOKING_TOOLS,
)

__all__ = [
    "GrokVoiceAgentSession",
    "GROK_VOICES",
    "GROK_REALISM_CUES",
    "GROK_BUILTIN_TOOLS",
    "DTMF_TOOL",
    "VOICE_BOOKING_TOOLS",
]
