"""Tests for public embed tool exposure and execution."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, status
from tribunal_widget.openai import build_embed_realtime_session, build_embed_tools
from tribunal_widget.schemas import EmbedActionResponse, ToolCallRequest
from tribunal_widget.service import PublicEmbedService


def _tool_names(tools: list[dict[str, object]]) -> list[str]:
    return [str(tool["name"]) for tool in tools]


def _embed_agent(*, enabled_tools: list[str] | None = None) -> MagicMock:
    agent = MagicMock()
    agent.id = "agent-id"
    agent.workspace_id = "workspace-id"
    agent.public_id = "demo-public-id"
    agent.allowed_domains = ["allowed.example"]
    agent.enabled_tools = enabled_tools or []
    agent.system_prompt = "You are helpful."
    agent.voice_id = "verse"
    agent.language = "en-US"
    agent.turn_detection_mode = "server_vad"
    agent.turn_detection_threshold = 0.5
    agent.silence_duration_ms = 500
    return agent


def test_build_embed_tools_always_includes_end_call_only_by_default() -> None:
    tools = build_embed_tools(_embed_agent())

    assert _tool_names(tools) == ["end_call"]


def test_build_embed_tools_gates_request_phone_demo() -> None:
    tools = build_embed_tools(_embed_agent(enabled_tools=["request_phone_demo"]))

    assert _tool_names(tools) == ["end_call", "request_phone_demo"]
    phone_tool = tools[1]
    assert "explicitly consents" in str(phone_tool["description"])
    assert phone_tool["parameters"] == {
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "The user's confirmed US phone number to call.",
            },
            "caller_name": {
                "type": "string",
                "description": "Optional name of the person requesting the call.",
            },
            "notes": {
                "type": "string",
                "description": "Optional concise context about what the visitor wants to automate.",
            },
        },
        "required": ["phone_number"],
    }


def test_build_embed_realtime_session_passes_embed_tools() -> None:
    session = build_embed_realtime_session(_embed_agent(enabled_tools=["request_phone_demo"]))

    assert _tool_names(session["tools"]) == ["end_call", "request_phone_demo"]
    assert session["tool_choice"] == "auto"


async def test_request_phone_demo_tool_validates_and_triggers_call() -> None:
    service = PublicEmbedService(MagicMock())
    service.get_agent_by_public_id = AsyncMock(
        return_value=_embed_agent(enabled_tools=["request_phone_demo"])
    )
    service.access.require_origin = MagicMock()
    service.access.enforce_chat_limit = AsyncMock()
    service.trigger_call = AsyncMock(
        return_value=EmbedActionResponse(
            success=True,
            message="Call initiated! You should receive a call within 10 seconds.",
        )
    )

    response = await service.execute_tool_call(
        public_id="demo-public-id",
        origin="https://allowed.example",
        client_ip="203.0.113.10",
        body=ToolCallRequest(
            tool_name="request_phone_demo",
            arguments={
                "phone_number": "(555) 123-4567",
                "caller_name": "Ada Lovelace",
                "notes": "Wants help with lead response.",
            },
        ),
    )

    assert response.success is True
    assert response.action == "request_phone_demo"
    assert response.message == "Call initiated! You should receive a call within 10 seconds."
    trigger_kwargs = service.trigger_call.await_args.kwargs
    assert trigger_kwargs["public_id"] == "demo-public-id"
    assert trigger_kwargs["origin"] == "https://allowed.example"
    assert trigger_kwargs["client_ip"] == "203.0.113.10"
    assert trigger_kwargs["body"].phone_number == "+15551234567"
    assert trigger_kwargs["body"].caller_name == "Ada Lovelace"


async def test_request_phone_demo_tool_rejects_disabled_agent() -> None:
    service = PublicEmbedService(MagicMock())
    service.get_agent_by_public_id = AsyncMock(return_value=_embed_agent(enabled_tools=[]))
    service.access.require_origin = MagicMock()
    service.access.enforce_chat_limit = AsyncMock()
    service.trigger_call = AsyncMock()

    response = await service.execute_tool_call(
        public_id="demo-public-id",
        origin="https://allowed.example",
        client_ip="203.0.113.10",
        body=ToolCallRequest(
            tool_name="request_phone_demo",
            arguments={"phone_number": "5551234567"},
        ),
    )

    assert response.success is False
    assert response.action == "request_phone_demo"
    assert response.result == {"error": "tool_not_enabled"}
    service.trigger_call.assert_not_awaited()


async def test_request_phone_demo_tool_returns_validation_failure() -> None:
    service = PublicEmbedService(MagicMock())
    service.get_agent_by_public_id = AsyncMock(
        return_value=_embed_agent(enabled_tools=["request_phone_demo"])
    )
    service.access.require_origin = MagicMock()
    service.access.enforce_chat_limit = AsyncMock()
    service.trigger_call = AsyncMock()

    response = await service.execute_tool_call(
        public_id="demo-public-id",
        origin="https://allowed.example",
        client_ip="203.0.113.10",
        body=ToolCallRequest(
            tool_name="request_phone_demo",
            arguments={"phone_number": "123"},
        ),
    )

    assert response.success is False
    assert response.action == "request_phone_demo"
    assert response.message == "Please provide a valid 10-digit US phone number before I can call."
    assert response.result == {"error": "invalid_phone_request"}
    service.trigger_call.assert_not_awaited()


async def test_request_phone_demo_tool_returns_call_failure() -> None:
    service = PublicEmbedService(MagicMock())
    service.get_agent_by_public_id = AsyncMock(
        return_value=_embed_agent(enabled_tools=["request_phone_demo"])
    )
    service.access.require_origin = MagicMock()
    service.access.enforce_chat_limit = AsyncMock()
    service.trigger_call = AsyncMock(
        side_effect=HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not available",
        )
    )

    response = await service.execute_tool_call(
        public_id="demo-public-id",
        origin="https://allowed.example",
        client_ip="203.0.113.10",
        body=ToolCallRequest(
            tool_name="request_phone_demo",
            arguments={"phone_number": "5551234567"},
        ),
    )

    assert response.success is False
    assert response.action == "request_phone_demo"
    assert response.message == "Voice service not available"
    assert response.result == {"error": "phone_demo_failed", "status_code": 503}
