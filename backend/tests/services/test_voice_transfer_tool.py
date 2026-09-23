"""Tests for the live warm/cold call transfer (AI -> human) tool."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.db.session as db_session_module
from app.models.agent import Agent
from app.models.conversation import Conversation, Message, MessageStatus
from app.models.workspace import Workspace
from app.services.ai.tool_executor import VoiceToolExecutor
from app.services.ai.voice_tools import get_tools_from_agent_config, is_transfer_enabled
from app.services.telephony.call_transfer import (
    PendingTransfer,
    build_briefing,
    make_transfer_leg_client_state,
    resolve_transfer_config,
    transfer_key_from_client_state,
)

_real_build_briefing = VoiceToolExecutor._build_transfer_briefing
_real_push_briefing = VoiceToolExecutor._push_transfer_briefing


def _make_agent(**overrides: Any) -> Agent:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "name": "Closer Bot",
        "description": "Hands hot leads to a human",
        "channel_mode": "voice",
        "voice_provider": "openai",
        "voice_id": "cedar",
        "language": "en-US",
        "system_prompt": "Be concise.",
        "temperature": 0.7,
        "text_response_delay_ms": 30_000,
        "text_max_context_messages": 20,
        "calcom_event_type_id": None,
        "enabled_tools": ["call_control"],
        "tool_settings": {"call_control": ["transfer_call"]},
        "transfer_destination_number": "+15551234567",
        "transfer_mode": "warm",
        "transfer_briefing_template": None,
        "is_active": True,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return Agent(**values)


def _make_call_message(agent: Agent) -> Message:
    conversation = Conversation(
        id=uuid.uuid4(),
        workspace_id=agent.workspace_id,
        workspace_phone="+15550001111",
        contact_phone="+15550002222",
        channel="voice",
        ai_enabled=True,
    )
    return Message(
        id=uuid.uuid4(),
        conversation=conversation,
        conversation_id=conversation.id,
        direction="inbound",
        channel="voice",
        body="",
        status=MessageStatus.ANSWERED,
        provider_message_id="caller-ccid-1",
        agent_id=agent.id,
        campaign_id=None,
        is_ai=True,
    )


class _ExecuteResult:
    def __init__(self, row: Any | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any | None:
        return self._row


class _SequencedSession:
    """Async session stub returning a queued sequence of scalar rows."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)
        self.added: list[Any] = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, *_args: Any, **_kwargs: Any) -> _ExecuteResult:
        row = self._rows.pop(0) if self._rows else None
        return _ExecuteResult(row)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def __aenter__(self) -> _SequencedSession:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False


# --------------------------------------------------------------------------- #
# Tool exposure
# --------------------------------------------------------------------------- #


def test_transfer_tool_exposed_only_when_enabled() -> None:
    enabled = _make_agent()
    disabled = _make_agent(
        enabled_tools=["call_control"], tool_settings={"call_control": ["send_dtmf"]}
    )

    assert "transfer_call" in {t["name"] for t in get_tools_from_agent_config(enabled)}
    assert "transfer_call" not in {t["name"] for t in get_tools_from_agent_config(disabled)}


def test_is_transfer_enabled_direct_and_integration_patterns() -> None:
    direct = _make_agent(enabled_tools=["transfer_call"], tool_settings={})
    integration = _make_agent()
    off = _make_agent(enabled_tools=[], tool_settings={})

    assert is_transfer_enabled(direct) is True
    assert is_transfer_enabled(integration) is True
    assert is_transfer_enabled(off) is False


# --------------------------------------------------------------------------- #
# Config resolution + briefing
# --------------------------------------------------------------------------- #


def test_resolve_transfer_config_prefers_agent_over_workspace() -> None:
    agent = _make_agent(transfer_destination_number="+15551112222", transfer_mode="cold")
    res = resolve_transfer_config(agent, {"transfer_destination_number": "+19998887777"})
    assert res is not None
    assert res.destination_number == "+15551112222"
    assert res.mode == "warm"  # operator cannot override the no-cold-dump rule


def test_resolve_transfer_config_falls_back_to_workspace() -> None:
    agent = _make_agent(transfer_destination_number=None, transfer_mode=None)
    res = resolve_transfer_config(
        agent, {"transfer_destination_number": "+19998887777", "transfer_mode": "warm"}
    )
    assert res is not None
    assert res.destination_number == "+19998887777"
    assert res.mode == "warm"


def test_resolve_transfer_config_returns_none_without_destination() -> None:
    agent = _make_agent(transfer_destination_number=None)
    assert resolve_transfer_config(agent, {}) is None
    assert resolve_transfer_config(agent, None) is None


def test_build_briefing_template_and_default() -> None:
    templated = build_briefing(
        template="{caller_name} wants {intent}.",
        caller_name="Dana",
        intent="a quote",
        summary="ignored",
    )
    assert templated == "Dana wants a quote."

    default = build_briefing(
        template=None, caller_name="Sam", intent="pricing", summary="Has a budget."
    )
    assert "Sam" in default
    assert "pricing" in default
    assert "Has a budget." in default


def test_pending_transfer_json_roundtrip() -> None:
    pending = PendingTransfer(
        caller_call_control_id="caller",
        closer_call_control_id="closer",
        workspace_id="ws",
        agent_id="ag",
        mode="warm",
        briefing="brief the human",
        language="en-US",
        created_at="2026-06-05T00:00:00+00:00",
    )
    restored = PendingTransfer.from_json(pending.to_json())
    assert restored == pending


# --------------------------------------------------------------------------- #
# Execution: consent and warm-only transfer
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def stub_briefing_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise handoff independently of the SMS network and database records."""
    monkeypatch.setattr(
        VoiceToolExecutor, "_build_transfer_briefing", AsyncMock(return_value="Lead brief")
    )
    monkeypatch.setattr(VoiceToolExecutor, "_push_transfer_briefing", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_cold_config_still_dials_warm_leg_after_consent() -> None:
    agent = _make_agent(transfer_mode="cold")
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})

    voice_service = AsyncMock()
    voice_service.dial_transfer_leg = AsyncMock(return_value="closer-leg")
    voice_service.get_call_control_application_id = AsyncMock(return_value="conn-1")
    voice_service.close = AsyncMock()

    audit = AsyncMock()

    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch(
            "app.services.telephony.telnyx_voice.TelnyxVoiceService",
            return_value=voice_service,
        ),
        patch("app.services.telephony.call_transfer.log_transfer_audit", audit),
        patch(
            "app.services.telephony.call_transfer.store_pending_transfer",
            AsyncMock(return_value=True),
        ),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            contact_info={"name": "Jane Doe"},
            call_control_id="caller-ccid-1",
            caller_consent_check=lambda quote: quote.startswith("Yes"),
        ).execute(
            "transfer_call",
            {
                "reason": "hot lead",
                "intent": "buy now",
                "caller_consented": True,
                "consent_quote": "Yes, connect me",
            },
        )

    assert result["success"] is True
    assert result["mode"] == "warm"
    voice_service.dial_transfer_leg.assert_awaited_once()
    kwargs = voice_service.dial_transfer_leg.await_args.kwargs
    assert kwargs["to_number"] == "+15551234567"
    assert kwargs["from_number"] == "+15550001111"
    audit.assert_awaited()
    assert audit.await_args.kwargs["decision"] == "dialed"
    voice_service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_without_consent_only_briefs_closer() -> None:
    agent = _make_agent(transfer_mode="cold")
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})

    voice_service = AsyncMock()
    voice_service.transfer_call = AsyncMock(return_value=False)
    voice_service.close = AsyncMock()

    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch(
            "app.services.telephony.telnyx_voice.TelnyxVoiceService",
            return_value=voice_service,
        ),
        patch("app.services.telephony.call_transfer.log_transfer_audit", AsyncMock()),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            call_control_id="caller-ccid-1",
        ).execute("transfer_call", {"reason": "human please"})

    assert result["success"] is True
    assert result["transferred"] is False
    voice_service.transfer_call.assert_not_awaited()
    voice_service.dial_transfer_leg.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Execution: warm transfer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_warm_transfer_dials_closer_and_stores_pending_state() -> None:
    agent = _make_agent(transfer_mode="warm")
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})

    voice_service = AsyncMock()
    voice_service.dial_transfer_leg = AsyncMock(return_value="closer-ccid-9")
    voice_service.get_call_control_application_id = AsyncMock(return_value="conn-1")
    voice_service.close = AsyncMock()

    store_pending = AsyncMock(return_value=True)

    async def dial_after_pending(**kwargs: Any) -> str:
        assert store_pending.await_count == 1
        token = store_pending.await_args.args[0].closer_call_control_id
        assert kwargs["client_state"] == make_transfer_leg_client_state(token)
        return "closer-ccid-9"

    voice_service.dial_transfer_leg.side_effect = dial_after_pending

    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch(
            "app.services.telephony.telnyx_voice.TelnyxVoiceService",
            return_value=voice_service,
        ),
        patch("app.services.telephony.call_transfer.store_pending_transfer", store_pending),
        patch("app.services.telephony.call_transfer.log_transfer_audit", AsyncMock()),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
        patch("app.core.config.settings.telnyx_connection_id", ""),
        patch("app.core.config.settings.api_base_url", "https://api.example.com"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            contact_info={"name": "Jane Doe"},
            call_control_id="caller-ccid-1",
            caller_consent_check=lambda quote: quote.startswith("Yes"),
        ).execute(
            "transfer_call",
            {
                "reason": "hot lead",
                "intent": "wants premium",
                "summary": "Budget 5k.",
                "caller_consented": True,
                "consent_quote": "Yes, please connect me",
            },
        )

    assert result["success"] is True
    assert result["mode"] == "warm"
    assert result["transferred"] is False
    assert result["handoff_pending"] is True
    voice_service.dial_transfer_leg.assert_awaited_once()
    dial_kwargs = voice_service.dial_transfer_leg.await_args.kwargs
    assert dial_kwargs["to_number"] == "+15551234567"
    assert dial_kwargs["from_number"] == "+15550001111"
    assert dial_kwargs["webhook_url"] == "https://api.example.com/webhooks/telnyx/voice"

    store_pending.assert_awaited_once()
    pending = store_pending.await_args.args[0]
    assert pending.caller_call_control_id == "caller-ccid-1"
    assert uuid.UUID(pending.closer_call_control_id)
    assert store_pending.await_args.args[0].closer_call_control_id == pending.closer_call_control_id
    assert dial_kwargs["client_state"] == make_transfer_leg_client_state(
        pending.closer_call_control_id
    )
    assert (
        transfer_key_from_client_state(dial_kwargs["client_state"])
        == pending.closer_call_control_id
    )
    assert pending.briefing == "Lead brief"


@pytest.mark.asyncio
async def test_warm_transfer_fails_gracefully_when_dial_fails() -> None:
    agent = _make_agent(transfer_mode="warm")
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})

    voice_service = AsyncMock()
    voice_service.dial_transfer_leg = AsyncMock(return_value=None)
    voice_service.get_call_control_application_id = AsyncMock(return_value="conn-1")
    voice_service.close = AsyncMock()

    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch(
            "app.services.telephony.telnyx_voice.TelnyxVoiceService",
            return_value=voice_service,
        ),
        patch(
            "app.services.telephony.call_transfer.store_pending_transfer",
            AsyncMock(return_value=True),
        ),
        patch("app.services.telephony.call_transfer.pop_pending_transfer", AsyncMock()),
        patch("app.services.telephony.call_transfer.log_transfer_audit", AsyncMock()),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
        patch("app.core.config.settings.telnyx_connection_id", "conn-1"),
        patch("app.core.config.settings.api_base_url", "https://api.example.com"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            call_control_id="caller-ccid-1",
            caller_consent_check=lambda quote: quote == "Yes, connect me",
        ).execute(
            "transfer_call",
            {"reason": "hot lead", "caller_consented": True, "consent_quote": "Yes, connect me"},
        )

    assert result["success"] is False
    assert "Could not reach a team member" in result["error"]


@pytest.mark.asyncio
async def test_consent_requires_a_quote() -> None:
    agent = _make_agent()
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})
    voice_service = AsyncMock()
    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch("app.services.telephony.telnyx_voice.TelnyxVoiceService", return_value=voice_service),
        patch("app.services.telephony.call_transfer.log_transfer_audit", AsyncMock()),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            call_control_id="caller-ccid-1",
            caller_consent_check=lambda quote: quote.startswith("Yes"),
        ).execute(
            "transfer_call",
            {"reason": "high intent", "caller_consented": True, "consent_quote": "  "},
        )
    assert result["transferred"] is False
    voice_service.dial_transfer_leg.assert_not_awaited()


@pytest.mark.asyncio
async def test_briefing_contains_workspace_contact_bant_objections_and_calendar() -> None:
    agent = _make_agent()
    contact = SimpleNamespace(
        source="inbound_call",
        qualification_signals={
            "budget": {"value": "$5k"},
            "authority": {"value": "owner"},
            "need": {"value": "new home"},
            "timeline": {"value": "this month"},
            "interest_level": "high",
            "objections": ["price"],
        },
    )
    opportunity = SimpleNamespace(name="House search", status="open")
    appointment = SimpleNamespace(
        status="scheduled", scheduled_at=datetime(2026, 10, 1, tzinfo=UTC)
    )
    with patch.object(
        db_session_module,
        "AsyncSessionLocal",
        side_effect=lambda: _SequencedSession([contact, opportunity, appointment]),
    ):
        briefing = await _real_build_briefing(
            VoiceToolExecutor(agent=agent),
            {"workspace_id": agent.workspace_id, "contact_id": 42},
            resolve_transfer_config(agent, {}),
            "ready to buy",
            "Asked about homes",
            {"budget": "My budget is $10k", "objections": "Concerned about fees"},
        )
    for fact in (
        "inbound_call",
        "$5k",
        "owner",
        "new home",
        "this month",
        "price",
        "House search",
        "scheduled",
        "ready to buy",
        "My budget is $10k",
        "Concerned about fees",
    ):
        assert fact in briefing


@pytest.mark.asyncio
async def test_failed_pending_state_never_hands_caller_to_human() -> None:
    agent = _make_agent()
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})
    voice_service = AsyncMock()
    voice_service.dial_transfer_leg = AsyncMock(return_value="closer-leg")
    voice_service.get_call_control_application_id = AsyncMock(return_value="conn-1")
    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch("app.services.telephony.telnyx_voice.TelnyxVoiceService", return_value=voice_service),
        patch(
            "app.services.telephony.call_transfer.store_pending_transfer",
            AsyncMock(return_value=False),
        ),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            call_control_id="caller-ccid-1",
            caller_consent_check=lambda quote: quote.startswith("Yes"),
        ).execute(
            "transfer_call",
            {
                "reason": "hot lead",
                "caller_consented": True,
                "consent_quote": "Yes, please connect me",
            },
        )
    assert result["success"] is False
    voice_service.dial_transfer_leg.assert_not_awaited()
    voice_service.bridge_calls.assert_not_awaited()


@pytest.mark.asyncio
async def test_transfer_rejects_mismatched_workspace() -> None:
    agent = _make_agent()
    call_message = _make_call_message(agent)
    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message]),
        ),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent, workspace_id=uuid.uuid4(), call_control_id="caller-ccid-1"
        ).execute("transfer_call", {"reason": "hot lead"})
    assert result["success"] is False
    assert "current call" in result["error"]


@pytest.mark.asyncio
async def test_sms_briefing_is_direct_and_does_not_write_customer_conversation() -> None:
    agent = _make_agent()
    ctx = {"workspace_id": agent.workspace_id, "workspace_phone": "+15550001111"}
    provider = AsyncMock()
    provider.send_internal_notification = AsyncMock(return_value=True)
    with patch("app.services.telephony.telnyx.TelnyxSMSService", return_value=provider):
        sent = await _real_push_briefing(
            VoiceToolExecutor(agent=agent, call_control_id="caller-ccid-1"),
            ctx,
            "+15551234567",
            "Lead brief",
        )
    assert sent is True
    assert provider.send_internal_notification.await_args.kwargs["to_number"] == "+15551234567"
    assert (
        provider.send_internal_notification.await_args.kwargs["body"]
        == "Live lead briefing: Lead brief"
    )
    provider.close.assert_awaited_once()


def test_transfer_consent_quote_must_match_latest_caller_utterance() -> None:
    from app.services.ai.voice_agent_base import VoiceAgentBase

    session = SimpleNamespace(
        _transcript_entries=[
            {"role": "user", "text": "Yes, that sounds good"},
            {"role": "assistant", "text": "Would you like the closer?"},
            {"role": "user", "text": "No, not now"},
        ]
    )
    assert not VoiceAgentBase.has_caller_consent(session, "Yes, that sounds good")
    assert not VoiceAgentBase.has_caller_consent(session, "No, not now")
    session._transcript_entries.append({"role": "user", "text": "Yes, connect me please"})
    assert VoiceAgentBase.has_caller_consent(session, "Yes, connect me please!")
    assert not VoiceAgentBase.has_caller_consent(session, "yes, connect another person")
    assert not VoiceAgentBase.has_caller_consent(session, "connect me yesterday")


@pytest.mark.asyncio
async def test_live_speech_triggers_once_on_high_intent_or_complete_bant() -> None:
    from app.services.ai.voice_agent_base import VoiceAgentBase

    callback = AsyncMock()
    session = SimpleNamespace(
        _hot_lead_callback=callback,
        _hot_lead_notified=False,
        _hot_lead_signals={},
        _sentiment_tasks=set(),
        logger=MagicMock(),
    )
    session._run_hot_lead_callback = lambda text: VoiceAgentBase._run_hot_lead_callback(
        session, text
    )
    for turn in (
        "My budget is $5000",
        "I am the buyer",
        "I need a home",
        "This month",
        "I'm ready to buy",
    ):
        VoiceAgentBase._check_live_hot_lead(session, turn)
    await asyncio.gather(*session._sentiment_tasks)
    callback.assert_awaited_once_with(
        "This month",
        {
            "budget": "My budget is $5000",
            "authority": "I am the buyer",
            "need": "I need a home",
            "timeline": "This month",
        },
    )

    session._hot_lead_notified = False
    session._hot_lead_signals.clear()
    callback.return_value = False
    VoiceAgentBase._check_live_hot_lead(session, "I am ready to buy")
    await asyncio.gather(*session._sentiment_tasks)
    assert session._hot_lead_notified is False  # failed SMS can retry next turn

    second = SimpleNamespace(
        _hot_lead_callback=AsyncMock(),
        _hot_lead_notified=False,
        _hot_lead_signals={},
        _sentiment_tasks=set(),
        logger=MagicMock(),
    )
    second._run_hot_lead_callback = lambda text: VoiceAgentBase._run_hot_lead_callback(second, text)
    VoiceAgentBase._check_live_hot_lead(second, "I am ready to buy")
    await asyncio.gather(*second._sentiment_tasks)
    second._hot_lead_callback.assert_awaited_once()

    third = SimpleNamespace(
        _hot_lead_callback=AsyncMock(),
        _hot_lead_notified=False,
        _hot_lead_signals={},
        _sentiment_tasks=set(),
        logger=MagicMock(),
    )
    third._run_hot_lead_callback = lambda text: VoiceAgentBase._run_hot_lead_callback(third, text)
    VoiceAgentBase._check_live_hot_lead(third, "I want to buy")
    await asyncio.gather(*third._sentiment_tasks)
    third._hot_lead_callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_voice_session_briefs_without_model_tool_call() -> None:
    from app.websockets.voice_bridge import _enable_hot_lead_briefing

    session = SimpleNamespace(set_hot_lead_callback=MagicMock())
    agent = _make_agent()
    with patch.object(
        VoiceToolExecutor, "execute", AsyncMock(return_value={"success": True})
    ) as execute:
        _enable_hot_lead_briefing(
            session,
            agent,
            {"name": "Jane"},
            "America/New_York",
            "caller-ccid-1",
            agent.workspace_id,
            MagicMock(),
        )
        callback = session.set_hot_lead_callback.call_args.args[0]
        await callback("I am ready to buy", {"budget": "My budget is $5000"})
    execute.assert_awaited_once()
    arguments = execute.await_args.args[1]
    assert arguments["caller_consented"] is False
    assert arguments["summary"] == "I am ready to buy"
    assert arguments["qualification"]["budget"] == "My budget is $5000"


@pytest.mark.asyncio
async def test_updated_briefing_uses_new_sms_idempotency_key() -> None:
    agent = _make_agent()
    provider = AsyncMock()
    provider.send_internal_notification = AsyncMock(return_value=True)
    ctx = {"workspace_phone": "+15550001111"}
    with patch("app.services.telephony.telnyx.TelnyxSMSService", return_value=provider):
        executor = VoiceToolExecutor(agent=agent, call_control_id="caller-ccid-1")
        await _real_push_briefing(executor, ctx, "+15551234567", "Budget $5k")
        await _real_push_briefing(executor, ctx, "+15551234567", "Budget $10k")
    sends = provider.send_internal_notification.await_args_list
    assert sends[0].kwargs["idempotency_key"] != sends[1].kwargs["idempotency_key"]


# --------------------------------------------------------------------------- #
# Execution: no destination configured
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_transfer_without_destination_is_blocked_and_audited() -> None:
    agent = _make_agent(transfer_destination_number=None, transfer_mode="warm")
    call_message = _make_call_message(agent)
    workspace = Workspace(id=agent.workspace_id, name="WS", slug="ws", settings={})

    audit = AsyncMock()

    with (
        patch.object(
            db_session_module,
            "AsyncSessionLocal",
            side_effect=lambda: _SequencedSession([call_message, workspace]),
        ),
        patch("app.services.telephony.call_transfer.log_transfer_audit", audit),
        patch("app.core.config.settings.telnyx_api_key", "key-123"),
    ):
        result = await VoiceToolExecutor(
            agent=agent,
            call_control_id="caller-ccid-1",
        ).execute("transfer_call", {"reason": "human please"})

    assert result["success"] is False
    assert "No human transfer destination" in result["error"]
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["decision"] == "blocked"
