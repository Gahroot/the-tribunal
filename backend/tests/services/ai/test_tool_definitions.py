"""Provider contracts and execution policy must derive from one typed definition."""

import json
from dataclasses import FrozenInstanceError
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from pydantic import Field, ValidationError

from app.services.ai.crm_assistant._tool_metadata import get_tool_policy
from app.services.ai.crm_assistant._tools import CRM_TOOLS, get_crm_tools
from app.services.ai.elevenlabs_voice_agent import ElevenLabsVoiceAgentSession
from app.services.ai.grok.session_config import GrokSessionConfigBuilder
from app.services.ai.text_tool_executor import _TOOL_SCHEMAS, TextToolExecutor
from app.services.ai.text_tool_executor import GATE_EXEMPT_TOOLS as TEXT_EXEMPT
from app.services.ai.tool_definition import ToolArguments, ToolDefinition
from app.services.ai.tool_definitions import TOOL_DEFINITIONS, gate_exempt_tools, tools_for_channel
from app.services.ai.tool_executor import GATE_EXEMPT_TOOLS as VOICE_EXEMPT
from app.services.ai.voice_tools import (
    VOICE_BOOKING_TOOLS,
    build_tools_list,
    get_booking_tools,
    get_text_booking_tools,
    get_text_search_knowledge_tool,
)


@pytest.mark.parametrize("definition", TOOL_DEFINITIONS.values(), ids=TOOL_DEFINITIONS.keys())
def test_provider_formats_share_the_same_contract(definition):
    openai = definition.render("openai")
    grok = definition.render("grok")
    elevenlabs = definition.render("elevenlabs")
    assert openai == {
        "type": "function",
        "function": {key: value for key, value in grok.items() if key != "type"},
    }
    assert elevenlabs == grok
    schema = grok["parameters"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema.get("required", [])) == {
        name for name, field in definition.arguments.model_fields.items() if field.is_required()
    }
    assert set(schema["properties"]) == set(definition.arguments.model_fields)
    assert "$ref" not in json.dumps(schema)
    assert "gate_exempt" not in grok
    assert "channels" not in grok


def test_gate_exemptions_are_explicit_and_channel_scoped():
    assert TOOL_DEFINITIONS["search_knowledge"].gate_exempt is True
    assert TEXT_EXEMPT == gate_exempt_tools("text") == {"search_knowledge"}
    assert (
        VOICE_EXEMPT
        == gate_exempt_tools("voice")
        == {"search_knowledge", "lookup_caller_record", "take_message", "check_payment_status"}
    )
    assert not gate_exempt_tools("crm")
    for name in ("book_appointment", "check_availability", "collect_payment", "transfer_call"):
        assert TOOL_DEFINITIONS[name].gate_exempt is False
    assert "unknown" not in TEXT_EXEMPT | VOICE_EXEMPT


def test_text_validation_uses_advertised_models():
    assert {tool.name: tool.arguments for tool in tools_for_channel("text")} == _TOOL_SCHEMAS
    args = (
        _TOOL_SCHEMAS["book_appointment"]
        .model_validate({"date": "2026-09-25", "time": "14:00", "email": "caller@example.test"})
        .model_dump(exclude_none=True)
    )
    assert args == {
        "date": "2026-09-25",
        "time": "14:00",
        "email": "caller@example.test",
        "duration_minutes": 30,
    }
    assert get_text_search_knowledge_tool() == TOOL_DEFINITIONS["search_knowledge"].render("openai")


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("search_knowledge", {"query": ""}),
        ("search_knowledge", {"query": "hours", "top_k": 11}),
        ("search_knowledge", {"query": "hours", "top_k": 0}),
        ("search_knowledge", {"query": "hours", "gate_exempt": True}),
        ("book_appointment", {"date": "2026-09-25", "time": "14:00"}),
        ("book_appointment", {"date": "", "time": "14:00", "email": "a@b.test"}),
        (
            "book_appointment",
            {
                "date": "2026-09-25",
                "time": "14:00",
                "email": "a@b.test",
                "duration_minutes": 0,
            },
        ),
        ("check_availability", {"start_date": ""}),
        ("check_availability", {"start_date": "2026-09-25", "contact_id": 123}),
    ],
)
def test_text_validation_preserves_rejections(name, arguments):
    with pytest.raises(ValidationError):
        _TOOL_SCHEMAS[name].model_validate_json(json.dumps(arguments))


def test_booking_contract_and_date_context_do_not_drift_between_channels():
    now = datetime(2026, 9, 24, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    with patch("app.services.ai.voice_tools.datetime") as clock:
        clock.now.return_value = now
        voice = get_booking_tools("not/a-timezone")
        clock.now.assert_called_once_with(ZoneInfo("America/New_York"))
        text = get_text_booking_tools("America/New_York")
    for realtime, chat, static in zip(voice, text, VOICE_BOOKING_TOOLS, strict=True):
        assert chat["function"] == {key: value for key, value in realtime.items() if key != "type"}
        assert "TODAY IS Thursday, September 24, 2026 (2026-09-24)" in realtime["description"]
        assert realtime["parameters"] == static["parameters"]
        assert "skill" in realtime["parameters"]["properties"]
    assert voice[0]["parameters"]["required"] == ["date", "time", "email"]


def test_rendered_schemas_are_independent_and_registry_is_immutable():
    definition = TOOL_DEFINITIONS["transfer_call"]
    first = definition.render("grok")
    first["parameters"]["properties"]["qualification"]["properties"].clear()
    first["parameters"]["required"].clear()
    second = definition.render("grok")
    assert "budget" in second["parameters"]["properties"]["qualification"]["properties"]
    assert second["parameters"]["required"] == ["reason", "caller_consented"]
    with pytest.raises(FrozenInstanceError):
        definition.gate_exempt = True
    with pytest.raises(TypeError):
        TOOL_DEFINITIONS["transfer_call"] = definition
    tools = build_tools_list(enable_search_knowledge=True)
    tools[1]["parameters"]["properties"].clear()
    assert "query" in build_tools_list(enable_search_knowledge=True)[1]["parameters"]["properties"]


def test_schema_metadata_does_not_erase_arguments_named_title():
    class Arguments(ToolArguments):
        title: str = Field(description="A real input, not schema metadata")

    definition = ToolDefinition("example", "Example", Arguments, frozenset({"text"}))
    assert definition.render("openai")["function"]["parameters"]["properties"] == {
        "title": {"type": "string", "description": "A real input, not schema metadata"}
    }
    assert definition.gate_exempt is False


def test_crm_contracts_keep_confirmation_policy():
    rendered = get_crm_tools()
    assert len(rendered) == len(CRM_TOOLS) == len(tools_for_channel("crm"))
    for tool in rendered:
        function = tool["function"]
        definition = TOOL_DEFINITIONS[function["name"]]
        assert function["description"] == definition.description
        has_confirmation = "confirmed" in function["parameters"]["properties"]
        assert has_confirmation == get_tool_policy(definition.name).requires_confirmation
    assert "confirmed" not in next(
        tool["function"]["parameters"]["properties"]
        for tool in rendered
        if tool["function"]["name"] == "create_checkout_link"
    )


def test_grok_builder_uses_generated_schemas_without_expanding_enabled_tools():
    builder = GrokSessionConfigBuilder(None, MagicMock())
    assert "tools" not in builder.with_tools().build()
    tools = builder.with_tools(enable_booking=True, ivr_detector_active=True).build()["tools"]
    assert [tool["name"] for tool in tools] == [
        "send_dtmf",
        "book_appointment",
        "check_availability",
    ]
    for tool in tools:
        assert tool["parameters"] == TOOL_DEFINITIONS[tool["name"]].render("grok")["parameters"]


@pytest.mark.asyncio
async def test_elevenlabs_session_uses_grok_wire_contract():
    session = object.__new__(ElevenLabsVoiceAgentSession)
    session.grok_ws = MagicMock()
    session._prompt_builder = MagicMock()
    session._prompt_builder.build_full_prompt.return_value = "Test prompt"
    session._enable_tools = True
    session.agent = None
    session.logger = MagicMock()
    session._send_to_grok = AsyncMock()
    await session._configure_grok_session()
    event = session._send_to_grok.await_args.args[0]
    assert event["type"] == "session.update"
    assert event["session"]["tools"] == [
        TOOL_DEFINITIONS[name].render("elevenlabs")
        for name in ("confirm_appointment", "book_appointment", "check_availability")
    ]


@pytest.mark.asyncio
async def test_text_gate_exemption_cannot_be_supplied_by_model():
    executor = object.__new__(TextToolExecutor)
    executor.log = MagicMock()
    executor.execute = AsyncMock(return_value={"success": True})
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_knowledge", arguments='{"query": "hours", "gate_exempt": true}'
        ),
    )
    with patch("app.services.ai.text_tool_executor.approval_gate_service") as gate:
        with pytest.raises(ValidationError):
            await executor.handle_tool_calls([call])
        executor.execute.assert_not_awaited()
        gate.check_and_execute_or_queue.assert_not_called()
        call.function.arguments = '{"query": "hours"}'
        await executor.handle_tool_calls([call])
        executor.execute.assert_awaited_once_with("search_knowledge", {"query": "hours"})
        gate.check_and_execute_or_queue.assert_not_called()
