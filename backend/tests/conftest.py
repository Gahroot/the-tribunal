"""Shared pytest fixtures for voice agent and audio tests.

This module provides common fixtures used across voice agent tests:
- Mock voice agent sessions
- Mock WebSocket connections
- Mock Cal.com service
- Mock Telnyx service
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_agent() -> MagicMock:
    """Create a mock Agent model for testing.

    Returns:
        MagicMock configured as an Agent model
    """
    agent = MagicMock()
    agent.id = "test-agent-id"
    agent.name = "Test Agent"
    agent.system_prompt = "You are a helpful assistant."
    agent.voice_id = "alloy"
    agent.voice_provider = "openai"
    agent.initial_greeting = "Hello, how can I help you today?"
    agent.temperature = 0.7
    agent.turn_detection_mode = "server_vad"
    agent.turn_detection_threshold = 0.5
    agent.silence_duration_ms = 700
    agent.calcom_event_type_id = "test-event-type"
    agent.enabled_tools = ["web_search"]
    agent.tool_settings = {}
    return agent


@pytest.fixture
def mock_contact_info() -> dict[str, Any]:
    """Create mock contact information for testing.

    Returns:
        Dictionary with contact fields
    """
    return {
        "name": "John Doe",
        "phone": "+15551234567",
        "email": "john@example.com",
        "company": "Acme Corp",
        "status": "active",
    }


@pytest.fixture
def mock_offer_info() -> dict[str, Any]:
    """Create mock offer information for testing.

    Returns:
        Dictionary with offer fields
    """
    return {
        "name": "Premium Plan",
        "description": "Our best plan with unlimited features",
        "discount_type": "percentage",
        "discount_value": 20.0,
        "terms": "Valid for new customers only",
    }


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Create a mock WebSocket for testing.

    Returns:
        AsyncMock configured as a WebSocket
    """
    websocket = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.client = MagicMock()
    websocket.client.host = "127.0.0.1"
    websocket.client.port = 12345
    return websocket


@pytest.fixture
def mock_calcom_service() -> AsyncMock:
    """Create a mock Cal.com service for testing.

    Returns:
        AsyncMock configured as CalComService
    """
    service = AsyncMock()
    service.get_availability = AsyncMock(
        return_value=[
            {"time": "09:00", "date": "2024-01-15"},
            {"time": "10:00", "date": "2024-01-15"},
            {"time": "14:00", "date": "2024-01-15"},
        ]
    )
    service.create_booking = AsyncMock(
        return_value={
            "uid": "booking-uid-123",
            "id": "booking-id-456",
        }
    )
    service.close = AsyncMock()
    return service


@pytest.fixture
def mock_telnyx_service() -> AsyncMock:
    """Create a mock Telnyx voice service for testing.

    Returns:
        AsyncMock configured as TelnyxVoiceService
    """
    service = AsyncMock()
    service.send_dtmf = AsyncMock(return_value=True)
    service.close = AsyncMock()
    return service


class MockVoiceAgentSession:
    """Mock voice agent session for testing.

    Implements the VoiceAgentProtocol interface for testing
    without actual WebSocket connections.
    """

    def __init__(self) -> None:
        self._connected = False
        self._tool_callback: Any = None
        self._audio_queue: list[bytes] = []
        self._transcript_entries: list[dict[str, Any]] = []

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def configure_session(
        self,
        voice: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        turn_detection_mode: str | None = None,
        turn_detection_threshold: float | None = None,
        silence_duration_ms: int | None = None,
    ) -> None:
        pass

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        pass

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        for chunk in self._audio_queue:
            yield chunk

    async def trigger_initial_response(
        self,
        greeting: str | None = None,
        is_outbound: bool = False,
    ) -> None:
        pass

    async def inject_context(
        self,
        contact_info: dict[str, Any] | None = None,
        offer_info: dict[str, Any] | None = None,
        is_outbound: bool = False,
    ) -> None:
        pass

    async def cancel_response(self) -> None:
        pass

    def is_connected(self) -> bool:
        return self._connected

    def get_transcript_json(self) -> str | None:
        if not self._transcript_entries:
            return None
        import json

        return json.dumps(self._transcript_entries)

    def set_tool_callback(self, callback: Any) -> None:
        self._tool_callback = callback

    async def submit_tool_result(
        self, call_id: str, result: dict[str, Any]
    ) -> None:
        pass

    def add_test_audio(self, audio: bytes) -> None:
        """Add audio to the mock queue for testing."""
        self._audio_queue.append(audio)

    def add_transcript_entry(self, role: str, text: str) -> None:
        """Add a transcript entry for testing."""
        self._transcript_entries.append({"role": role, "text": text})


@pytest.fixture
def mock_voice_session() -> MockVoiceAgentSession:
    """Create a mock voice agent session for testing.

    Returns:
        MockVoiceAgentSession instance
    """
    return MockVoiceAgentSession()
