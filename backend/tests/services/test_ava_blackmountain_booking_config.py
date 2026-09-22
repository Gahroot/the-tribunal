"""Tests for the Ava / Black Mountain Solutions booking configuration.

Locks in the agent shape written by ``scripts/ops/configure_ava_blackmountain.py``
so a future edit cannot quietly stop Ava from being able to book.

The two gates that matter differ by channel:

* OpenAI realtime voice (``voice_agent.py``) calls
  ``get_tools_from_agent_config(..., enable_booking=bool(agent.calcom_event_type_id))``
  so the booking tools hang off the event type id alone.
* Text/SMS (``text_response_generator.py``) additionally requires
  ``"book_appointment" in agent.enabled_tools``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.config import settings
from app.models.agent import Agent
from app.services.ai.text_response_generator import text_booking_enabled
from app.services.ai.voice_tools import get_tools_from_agent_config
from scripts.ops.configure_ava_blackmountain import (
    AVA_SYSTEM_PROMPT,
    BOOKINGS_TOOL_SETTINGS,
    REQUIRED_TOOLS,
    _apply_booking_fields,
)

# Arbitrary stand-in. The real id lives in production and in the script's
# docstring; tests assert the script *propagates whatever id it is given*,
# rather than restating a production constant that would drift silently.
EVENT_TYPE_ID = 4242424


def _make_ava(**overrides: Any) -> Agent:
    """Ava's production row as the ops script leaves it."""
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "name": "Ava",
        "channel_mode": "voice",
        "voice_provider": "openai",
        "voice_id": "marin",
        "language": "en-US",
        "realtime_model": "gpt-realtime-2.1",
        "system_prompt": AVA_SYSTEM_PROMPT,
        "temperature": 0.7,
        "calcom_event_type_id": EVENT_TYPE_ID,
        "assignment_strategy": "single",
        "enabled_tools": list(REQUIRED_TOOLS),
        "tool_settings": {"bookings": list(BOOKINGS_TOOL_SETTINGS)},
        "is_active": True,
    }
    values.update(overrides)
    return Agent(**values)


def _tool_names(tools: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for tool in tools:
        name = tool.get("name") or (tool.get("function") or {}).get("name")
        if name:
            names.add(name)
    return names


class TestVoiceBookingTools:
    def test_booking_tools_exposed_for_configured_agent(self) -> None:
        agent = _make_ava()

        tools = get_tools_from_agent_config(
            agent,
            enable_booking=bool(agent.calcom_event_type_id),
            timezone="America/New_York",
        )

        names = _tool_names(tools)
        assert "check_availability" in names
        assert "book_appointment" in names

    def test_no_booking_tools_without_event_type(self) -> None:
        """Ava's pre-change state: enabled_tools alone must not expose booking."""
        agent = _make_ava(calcom_event_type_id=None, enabled_tools=["book_appointment"])

        tools = get_tools_from_agent_config(
            agent,
            enable_booking=bool(agent.calcom_event_type_id),
            timezone="America/New_York",
        )

        names = _tool_names(tools)
        assert "check_availability" not in names
        assert "book_appointment" not in names


class TestScriptWritesBookingFields:
    """Exercise the ops script's own mutation, so the agent shape the other
    tests assume is the shape the script actually produces."""

    def test_apply_booking_fields_sets_every_gate(self) -> None:
        agent = _make_ava(
            calcom_event_type_id=None,
            assignment_strategy=None,
            enabled_tools=["book_appointment"],
            tool_settings={},
        )

        changed = _apply_booking_fields(agent, EVENT_TYPE_ID)

        assert changed is True
        assert agent.calcom_event_type_id == EVENT_TYPE_ID
        assert agent.assignment_strategy == "single"
        assert set(REQUIRED_TOOLS).issubset(set(agent.enabled_tools))
        assert agent.tool_settings["bookings"] == BOOKINGS_TOOL_SETTINGS

    def test_apply_booking_fields_is_idempotent(self) -> None:
        agent = _make_ava()

        assert _apply_booking_fields(agent, EVENT_TYPE_ID) is False

    def test_apply_booking_fields_preserves_unrelated_tools(self) -> None:
        agent = _make_ava(enabled_tools=["transfer_call"], tool_settings={"call_control": ["x"]})

        _apply_booking_fields(agent, EVENT_TYPE_ID)

        assert "transfer_call" in agent.enabled_tools
        assert agent.tool_settings["call_control"] == ["x"]


class TestTextChannelGate:
    """Exercises the real gate from text_response_generator, not a copy of it."""

    def test_gate_open_for_configured_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "calcom_api_key", "cal_live_test", raising=False)

        assert text_booking_enabled(_make_ava()) is True

    def test_gate_closed_without_book_appointment_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "calcom_api_key", "cal_live_test", raising=False)
        agent = _make_ava(enabled_tools=["bookings", "check_availability"])

        assert text_booking_enabled(agent) is False

    def test_gate_closed_without_event_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "calcom_api_key", "cal_live_test", raising=False)

        assert text_booking_enabled(_make_ava(calcom_event_type_id=None)) is False

    def test_gate_closed_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Matches the missing_calcom_api_key startup warning in app/main.py."""
        monkeypatch.setattr(settings, "calcom_api_key", "", raising=False)

        assert text_booking_enabled(_make_ava()) is False


class TestAvaPrompt:
    @pytest.mark.parametrize(
        "phrase",
        [
            "check_availability",
            "book_appointment",
            "EMAIL IS REQUIRED",
            "free 30-minute consultation",
        ],
    )
    def test_prompt_carries_booking_rules(self, phrase: str) -> None:
        """voice_agent builds Ava's prompt with include_booking=False, so the
        shared Cal.com block is never injected. The rules must be in her prompt."""
        assert phrase in AVA_SYSTEM_PROMPT

    @pytest.mark.parametrize(
        "claim",
        [
            "Food Nanny",
            "Advanced Window Products",
            "Luxury Rally Club",
            "Anchor Mill",
            "299 S Main",
            "435-800-5807",
            "Elijah",
            "Sam",
        ],
    )
    def test_prompt_omits_unconfirmed_claims(self, claim: str) -> None:
        """Client names, team members and contact details were not approved."""
        assert claim not in AVA_SYSTEM_PROMPT

    def test_prompt_keeps_no_invention_guardrail(self) -> None:
        assert "Never invent prices" in AVA_SYSTEM_PROMPT

    def test_prompt_states_not_an_investment_adviser(self) -> None:
        assert "NOT an investment adviser" in AVA_SYSTEM_PROMPT
