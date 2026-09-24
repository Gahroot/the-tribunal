"""Malformed model tool frames must never execute realtime actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.elevenlabs_voice_agent import ElevenLabsVoiceAgentSession
from app.services.ai.grok.session import GrokVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_type", "method", "payload"),
    [
        (
            VoiceAgentSession,
            "_handle_function_call_arguments_done",
            {"call_id": "call-1", "name": "book_appointment", "arguments": "[]"},
        ),
        (
            ElevenLabsVoiceAgentSession,
            "_handle_function_call",
            {"call_id": "call-1", "name": "book_appointment", "arguments": "[]"},
        ),
        (
            GrokVoiceAgentSession,
            "_handle_function_call",
            {"call_id": "call-1", "name": "book_appointment", "arguments": "[]"},
        ),
    ],
)
async def test_realtime_tool_rejects_non_object_arguments(session_type, method, payload) -> None:
    session = object.__new__(session_type)
    session.logger = MagicMock()
    session._tool_callback = AsyncMock()
    session.submit_tool_result = AsyncMock()
    await getattr(session, method)(payload)
    session._tool_callback.assert_not_awaited()
    session.submit_tool_result.assert_awaited_once()
    assert session.submit_tool_result.await_args.args[1]["success"] is False
