"""Configuration validation for automations.

An automation is only *ready* when the worker can actually execute every part
of it: the trigger is one the worker evaluates, its required trigger settings
are present, and every action is a supported type with its required settings.

``static_config_issues`` needs no database and is used both at the API
boundary and to report draft/incomplete state on every response.
``workspace_config_issues`` adds workspace-scoped reference checks (the
campaign/agent an action points at must exist in the same workspace) and is
only run on writes that would leave the automation active.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.campaign import Campaign
from app.services.automations.events import (
    EVENT_KNOWLEDGE_DOCUMENT_UPLOADED,
    EVENT_ROLEPLAY_COMPLETED,
)

# Triggers the worker evaluates (polling + event). The generic legacy kinds
# ("event", "schedule", "condition") are accepted for stored rows but never
# executed, so they cannot be activated.
POLLING_TRIGGERS = frozenset(
    {"appointment_booked", "booking_created", "no_show", "contact_tagged", "never_booked"}
)
LEGACY_TRIGGERS = frozenset({"event", "schedule", "condition"})

# Event triggers that never carry a contact, so contact actions cannot run.
CONTACTLESS_TRIGGERS = frozenset({EVENT_ROLEPLAY_COMPLETED, EVENT_KNOWLEDGE_DOCUMENT_UPLOADED})

# Action types the worker executes. All of them target a contact.
SUPPORTED_ACTION_TYPES = frozenset(
    {"send_sms", "send_email", "make_call", "enroll_campaign", "apply_tag", "add_tag"}
)

MIN_INACTIVITY_DAYS = 1
MAX_INACTIVITY_DAYS = 365


@dataclass(frozen=True, slots=True)
class AutomationConfigIssue:
    """One reason an automation cannot be activated."""

    code: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    return value.strip() if isinstance(value, str) else ""


def _parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _trigger_issues(
    trigger_type: str, trigger_config: dict[str, Any]
) -> list[AutomationConfigIssue]:
    trigger = trigger_type.lower()
    issues: list[AutomationConfigIssue] = []
    if trigger in LEGACY_TRIGGERS:
        issues.append(
            AutomationConfigIssue(
                code="unsupported_trigger",
                field="trigger_type",
                message=(
                    f"The '{trigger_type}' trigger is not run by the automation engine. "
                    "Choose a specific trigger such as No-show or Contact Tagged."
                ),
            )
        )
    elif trigger == "contact_tagged" and not _text(trigger_config, "tag"):
        issues.append(
            AutomationConfigIssue(
                code="missing_trigger_tag",
                field="trigger_config.tag",
                message="Enter the tag that should start this automation.",
            )
        )
    elif trigger == "never_booked" and "inactivity_days" in trigger_config:
        raw = trigger_config.get("inactivity_days")
        try:
            days = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            days = 0
        if isinstance(raw, bool) or not MIN_INACTIVITY_DAYS <= days <= MAX_INACTIVITY_DAYS:
            issues.append(
                AutomationConfigIssue(
                    code="invalid_inactivity_days",
                    field="trigger_config.inactivity_days",
                    message=(
                        f"Inactivity days must be a whole number between "
                        f"{MIN_INACTIVITY_DAYS} and {MAX_INACTIVITY_DAYS}."
                    ),
                )
            )
    return issues


def _action_issues(  # noqa: PLR0912 - one branch per supported action type
    index: int, action: dict[str, Any], trigger: str
) -> list[AutomationConfigIssue]:
    action_type = str(action.get("type", "")).lower()
    raw_config = action.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    prefix = f"actions[{index}]"
    step = f"Step {index + 1}"
    issues: list[AutomationConfigIssue] = []

    if action_type not in SUPPORTED_ACTION_TYPES:
        return [
            AutomationConfigIssue(
                code="unsupported_action",
                field=f"{prefix}.type",
                message=(
                    f"{step}: '{action_type or 'unknown'}' steps are not run by the "
                    "automation engine. Remove or replace this step."
                ),
            )
        ]

    if trigger in CONTACTLESS_TRIGGERS:
        issues.append(
            AutomationConfigIssue(
                code="action_requires_contact",
                field=f"{prefix}.type",
                message=(
                    f"{step}: this trigger has no contact, so contact actions "
                    "cannot run. Choose a contact-based trigger."
                ),
            )
        )

    if action_type == "send_sms" and not _text(config, "message"):
        issues.append(
            AutomationConfigIssue(
                code="missing_sms_message",
                field=f"{prefix}.config.message",
                message=f"{step}: write the text message to send.",
            )
        )
    elif action_type == "send_email":
        if not _text(config, "subject"):
            issues.append(
                AutomationConfigIssue(
                    code="missing_email_subject",
                    field=f"{prefix}.config.subject",
                    message=f"{step}: enter an email subject.",
                )
            )
        if not (_text(config, "message") or _text(config, "body")):
            issues.append(
                AutomationConfigIssue(
                    code="missing_email_body",
                    field=f"{prefix}.config.message",
                    message=f"{step}: write the email body.",
                )
            )
    elif action_type == "make_call":
        agent_id = config.get("agent_id")
        if agent_id not in (None, "") and _parse_uuid(agent_id) is None:
            issues.append(
                AutomationConfigIssue(
                    code="invalid_agent",
                    field=f"{prefix}.config.agent_id",
                    message=f"{step}: choose a valid voice agent.",
                )
            )
    elif action_type == "enroll_campaign":
        if _parse_uuid(config.get("campaign_id")) is None:
            issues.append(
                AutomationConfigIssue(
                    code="missing_campaign",
                    field=f"{prefix}.config.campaign_id",
                    message=f"{step}: choose the campaign to enroll contacts in.",
                )
            )
    elif action_type in ("apply_tag", "add_tag") and not _text(config, "tag"):
        issues.append(
            AutomationConfigIssue(
                code="missing_action_tag",
                field=f"{prefix}.config.tag",
                message=f"{step}: enter the tag to apply.",
            )
        )
    return issues


def static_config_issues(
    trigger_type: str,
    trigger_config: dict[str, Any] | None,
    actions: list[dict[str, Any]] | None,
) -> list[AutomationConfigIssue]:
    """Return every reason the automation cannot run, without touching the DB."""
    issues = _trigger_issues(trigger_type, trigger_config or {})
    action_list = actions or []
    if not action_list:
        issues.append(
            AutomationConfigIssue(
                code="missing_actions",
                field="actions",
                message="Add at least one action.",
            )
        )
    trigger = trigger_type.lower()
    for index, action in enumerate(action_list):
        issues.extend(_action_issues(index, action, trigger))
    return issues


async def workspace_config_issues(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    actions: list[dict[str, Any]] | None,
) -> list[AutomationConfigIssue]:
    """Check that campaigns/agents referenced by actions exist in the workspace."""
    issues: list[AutomationConfigIssue] = []
    for index, action in enumerate(actions or []):
        action_type = str(action.get("type", "")).lower()
        raw_config = action.get("config")
        config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
        step = f"Step {index + 1}"
        if action_type == "enroll_campaign":
            campaign_id = _parse_uuid(config.get("campaign_id"))
            if campaign_id is None:
                continue
            found = await db.scalar(
                select(Campaign.id).where(
                    Campaign.id == campaign_id, Campaign.workspace_id == workspace_id
                )
            )
            if found is None:
                issues.append(
                    AutomationConfigIssue(
                        code="campaign_not_found",
                        field=f"actions[{index}].config.campaign_id",
                        message=f"{step}: the selected campaign no longer exists.",
                    )
                )
        elif action_type == "make_call":
            agent_id = _parse_uuid(config.get("agent_id")) if config.get("agent_id") else None
            if agent_id is None:
                continue
            found = await db.scalar(
                select(Agent.id).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
            )
            if found is None:
                issues.append(
                    AutomationConfigIssue(
                        code="agent_not_found",
                        field=f"actions[{index}].config.agent_id",
                        message=f"{step}: the selected voice agent no longer exists.",
                    )
                )
    return issues
