"""Unit tests for the autonomous-message decision/trace builders and draft."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.outbound.message_trace import (
    OutboundTraceDraft,
    build_conversation_state,
    build_mandate_authorization,
)


def _draft() -> OutboundTraceDraft:
    return OutboundTraceDraft(workspace_id=uuid.uuid4(), conversation_id=uuid.uuid4())


def test_set_prompt_fingerprints_and_records_sections() -> None:
    draft = _draft()
    draft.set_prompt(
        system_prompt="You are the agent.",
        booking_instructions_included=True,
        knowledge_preamble_included=False,
    )

    assert draft.prompt["system_prompt"] == "You are the agent."
    assert draft.prompt["system_prompt_chars"] == len("You are the agent.")
    assert len(draft.prompt["system_prompt_sha256"]) == 64
    assert draft.prompt["booking_instructions_included"] is True
    assert draft.prompt["knowledge_preamble_included"] is False


def test_set_model_params_records_key_sampling_params() -> None:
    draft = _draft()
    draft.set_model_params(
        model="gpt-5.4-nano",
        temperature=0.3,
        max_completion_tokens=500,
        tool_choice="auto",
        timeout_seconds=30.0,
    )

    assert draft.model_params == {
        "model": "gpt-5.4-nano",
        "temperature": 0.3,
        "max_completion_tokens": 500,
        "tool_choice": "auto",
        "timeout_seconds": 30.0,
    }


def test_add_knowledge_passages_truncates_and_caps() -> None:
    draft = _draft()
    long_content = "x" * 5000
    passages = [{"title": f"doc{i}", "content": long_content, "score": 0.5} for i in range(30)]

    draft.add_knowledge_passages(passages, query="pricing")

    # Capped at 20 snippets, content truncated to 2000 chars.
    assert len(draft.knowledge_snippets) == 20
    assert all(len(s["content"]) == 2000 for s in draft.knowledge_snippets)
    assert draft.knowledge_snippets[0]["query"] == "pricing"
    assert draft.knowledge_snippets[0]["source"] == "search_knowledge"


def test_build_mandate_authorization_default_authorizes_reply() -> None:
    auth = build_mandate_authorization(None, last_inbound_body="how much for 500 ads?")

    assert auth["source"] == "autonomy_mandate"
    assert auth["enabled"] is True
    assert auth["authorized_rule"] == "act_and_report.conversation_reply"
    assert auth["requires_escalation"] is False
    assert auth["escalation_matches"] == []


def test_build_mandate_authorization_flags_escalation_keyword() -> None:
    auth = build_mandate_authorization(
        None, last_inbound_body="can you also run ads and do consulting?"
    )

    assert auth["requires_escalation"] is True
    keys = {match["key"] for match in auth["escalation_matches"]}
    assert {"ad_management", "consulting"} <= keys


def test_build_mandate_authorization_disabled_mandate() -> None:
    auth = build_mandate_authorization({"enabled": False}, last_inbound_body="hi")

    assert auth["enabled"] is False
    assert auth["authorized_rule"] == "disabled"


def test_build_conversation_state_snapshots_last_inbound() -> None:
    agent_id = uuid.uuid4()
    inbound_id = uuid.uuid4()
    conversation = SimpleNamespace(
        status="active",
        channel="imessage",
        ai_enabled=True,
        ai_paused=False,
        assigned_agent_id=agent_id,
        contact_id=42,
        followup_count_sent=1,
    )
    last_inbound = SimpleNamespace(id=inbound_id, body="interested!", created_at=None)

    state = build_conversation_state(conversation, last_inbound=last_inbound, message_count=7)

    assert state["channel"] == "imessage"
    assert state["assigned_agent_id"] == str(agent_id)
    assert state["message_count"] == 7
    assert state["last_inbound"]["message_id"] == str(inbound_id)
    assert state["last_inbound"]["body"] == "interested!"


def test_build_conversation_state_handles_no_inbound() -> None:
    conversation = SimpleNamespace(
        status="active",
        channel="sms",
        ai_enabled=True,
        ai_paused=False,
        assigned_agent_id=None,
        contact_id=None,
        followup_count_sent=0,
    )

    state = build_conversation_state(conversation, last_inbound=None)

    assert state["last_inbound"] is None
    assert state["assigned_agent_id"] is None
