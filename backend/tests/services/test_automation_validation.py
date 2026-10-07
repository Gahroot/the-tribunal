"""Readiness rules for automations (RF-013).

An automation is only "ready" when the worker can execute it; these rules
gate activation at the API and are re-checked by the worker.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.automations.validation import static_config_issues


def _codes(trigger: str, trigger_config: dict, actions: list[dict]) -> list[str]:
    return [i.code for i in static_config_issues(trigger, trigger_config, actions)]


def test_default_send_sms_automation_with_empty_config_is_incomplete() -> None:
    """The form's first-use default (no_show + empty send_sms) cannot run."""
    issues = static_config_issues("no_show", {}, [{"type": "send_sms", "config": {}}])

    assert [i.code for i in issues] == ["missing_sms_message"]
    assert issues[0].field == "actions[0].config.message"
    assert "text message" in issues[0].message


def test_default_send_sms_automation_with_message_is_ready() -> None:
    assert _codes("no_show", {}, [{"type": "send_sms", "config": {"message": "Hi"}}]) == []


def test_whitespace_only_message_is_incomplete() -> None:
    assert _codes("no_show", {}, [{"type": "send_sms", "config": {"message": "  "}}]) == [
        "missing_sms_message"
    ]


def test_no_actions_is_incomplete() -> None:
    assert _codes("no_show", {}, []) == ["missing_actions"]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ({"type": "send_email", "config": {}}, ["missing_email_subject", "missing_email_body"]),
        ({"type": "send_email", "config": {"subject": "S", "body": "B"}}, []),
        ({"type": "send_email", "config": {"subject": "S", "message": "B"}}, []),
        ({"type": "enroll_campaign", "config": {}}, ["missing_campaign"]),
        ({"type": "enroll_campaign", "config": {"campaign_id": "nope"}}, ["missing_campaign"]),
        ({"type": "enroll_campaign", "config": {"campaign_id": str(uuid.uuid4())}}, []),
        ({"type": "apply_tag", "config": {}}, ["missing_action_tag"]),
        ({"type": "add_tag", "config": {"tag": "vip"}}, []),
        ({"type": "make_call", "config": {}}, []),
        ({"type": "make_call", "config": {"agent_id": "not-a-uuid"}}, ["invalid_agent"]),
        ({"type": "wait", "config": {"hours": 1}}, ["unsupported_action"]),
        ({"type": "webhook", "config": {}}, ["unsupported_action"]),
    ],
)
def test_action_requirements(action: dict, expected: list[str]) -> None:
    assert _codes("no_show", {}, [action]) == expected


def test_every_action_is_checked_not_only_the_first() -> None:
    issues = static_config_issues(
        "no_show",
        {},
        [
            {"type": "send_sms", "config": {"message": "Hi"}},
            {"type": "apply_tag", "config": {}},
        ],
    )
    assert [(i.code, i.field) for i in issues] == [("missing_action_tag", "actions[1].config.tag")]


@pytest.mark.parametrize(
    ("trigger", "config", "expected"),
    [
        ("contact_tagged", {}, ["missing_trigger_tag"]),
        ("contact_tagged", {"tag": "hot"}, []),
        ("never_booked", {}, []),
        ("never_booked", {"inactivity_days": 14}, []),
        ("never_booked", {"inactivity_days": 0}, ["invalid_inactivity_days"]),
        ("never_booked", {"inactivity_days": "x"}, ["invalid_inactivity_days"]),
        ("event", {}, ["unsupported_trigger"]),
        ("schedule", {}, ["unsupported_trigger"]),
        ("missed_call", {}, []),
    ],
)
def test_trigger_requirements(trigger: str, config: dict, expected: list[str]) -> None:
    actions = [{"type": "apply_tag", "config": {"tag": "x"}}]
    assert _codes(trigger, config, actions) == expected


def test_contactless_trigger_cannot_run_contact_actions() -> None:
    assert _codes("roleplay_completed", {}, [{"type": "apply_tag", "config": {"tag": "x"}}]) == [
        "action_requires_contact"
    ]
