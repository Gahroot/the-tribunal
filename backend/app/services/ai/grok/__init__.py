"""Grok voice agent package.

This package provides the Grok (xAI) Realtime API integration for voice conversations.
The main entry point is GrokVoiceAgentSession, which is also re-exported from the
parent module for backward compatibility.

Modules:
    session: Main GrokVoiceAgentSession class
    constants: Voice configurations, tool definitions
    session_config: Session configuration builder
    dtmf_handler: DTMF detection and sending
    event_handlers: Event handler registry
    ivr_mode_controller: IVR mode switching
    audio_stream: Audio streaming utilities
"""

from app.services.ai.grok.session import GrokVoiceAgentSession

__all__ = ["GrokVoiceAgentSession"]
