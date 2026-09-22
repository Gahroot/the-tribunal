"""Workspace autonomy mandate policy helpers.

The autonomy mandate is the single workspace-level object that decides whether
The Tribunal acts-and-reports or parks an action for human approval.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

AUTONOMY_MANDATE_VERSION = 1
AUTONOMY_MANDATE_ACTION_SOURCE = "autonomy_mandate"

FIRST_TOUCH_ACTION_TYPES = frozenset(
    {
        "outbound.launch_campaign",
        "send_initial_message",
        "crm_assistant.send_initial_message",
    }
)

BATCH_CLOSE_ACTION_TYPES = frozenset(
    {
        "collect_payment",
        "create_checkout_link",
        "send_checkout_link",
        "stripe_checkout.create_checkout_link",
        "stripe_checkout.send_checkout_link",
        "crm_assistant.create_checkout_link",
        "crm_assistant.send_checkout_link",
    }
)

BATCH_PACKS: tuple[dict[str, Any], ...] = (
    {"pack_key": "sampler_100", "label": "100 ads", "ad_count": 100, "price_cents": 49_700},
    {"pack_key": "growth_300", "label": "300 ads", "ad_count": 300, "price_cents": 149_700},
    {"pack_key": "anchor_500", "label": "500 ads", "ad_count": 500, "price_cents": 250_000},
    {"pack_key": "scale_1000", "label": "1,000 ads", "ad_count": 1000, "price_cents": 399_700},
)

DEFAULT_ESCALATION_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "ad_management",
        "label": "Buyer wants ad-management / media buying / someone to run ads",
        "keywords": ["run ads", "manage ads", "media buying", "ad management", "campaign setup"],
    },
    {
        "key": "ai_agent_install",
        "label": "Buyer wants AI-agent installation or automation buildout",
        "keywords": ["install ai", "ai agent", "set up an agent", "automation build", "chatbot"],
    },
    {
        "key": "consulting",
        "label": "Buyer wants consulting or custom services beyond the batch",
        "keywords": ["consulting", "done for you", "strategy call", "custom service", "coach me"],
    },
)


def default_autonomy_mandate() -> dict[str, Any]:
    """Return the default full-autonomy mandate for standard batch-pack sales."""

    return {
        "version": AUTONOMY_MANDATE_VERSION,
        "enabled": True,
        "posture": "act_and_report",
        "auto_send_first_touches": True,
        "auto_close_batch_packs": True,
        "default_offer_id": None,
        "batch_pack_anchor_key": "anchor_500",
        "batch_pack_max_price_cents": 399_700,
        "allowed_batch_packs": copy.deepcopy(list(BATCH_PACKS)),
        "daily_send_cap": 100,
        "quiet_hours": {
            "enabled": True,
            "timezone": "America/New_York",
            "start": "20:00",
            "end": "08:00",
        },
        "escalation_rules": copy.deepcopy(list(DEFAULT_ESCALATION_RULES)),
        "operator_report": {
            "enabled": True,
            "channel": "sms",
            "phone": None,
            "events": ["payment_succeeded", "human_escalation"],
        },
    }


def prestyj_autonomy_mandate(
    *, offer_id: str | None = None, operator_phone: str | None = None
) -> dict[str, Any]:
    """Return the Prestyj Batch Video Ads mandate used by the deterministic seed."""

    mandate = default_autonomy_mandate()
    mandate.update(
        {
            "default_offer_id": offer_id,
            "description": (
                "Autonomously run Prestyj Batch Video Ads sales over iMessage: discover, "
                "first-touch, objection-handle, anchor-close, Stripe payment, and report."
            ),
        }
    )
    mandate["operator_report"]["phone"] = operator_phone
    return mandate


def normalize_autonomy_mandate(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge a stored mandate with defaults and coerce risky values into bounds."""

    mandate = default_autonomy_mandate()
    if raw:
        mandate.update(dict(raw))

    mandate["version"] = AUTONOMY_MANDATE_VERSION
    mandate["enabled"] = bool(mandate.get("enabled", True))
    mandate["auto_send_first_touches"] = bool(mandate.get("auto_send_first_touches", True))
    mandate["auto_close_batch_packs"] = bool(mandate.get("auto_close_batch_packs", True))
    mandate["daily_send_cap"] = _bounded_int(
        mandate.get("daily_send_cap"), default=100, minimum=1, maximum=10_000
    )
    mandate["batch_pack_max_price_cents"] = _bounded_int(
        mandate.get("batch_pack_max_price_cents"),
        default=399_700,
        minimum=0,
        maximum=10_000_000,
    )
    if not isinstance(mandate.get("quiet_hours"), dict):
        mandate["quiet_hours"] = default_autonomy_mandate()["quiet_hours"]
    if not isinstance(mandate.get("escalation_rules"), list):
        mandate["escalation_rules"] = copy.deepcopy(list(DEFAULT_ESCALATION_RULES))
    if not isinstance(mandate.get("operator_report"), dict):
        mandate["operator_report"] = default_autonomy_mandate()["operator_report"]
    return mandate


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(integer, maximum))


def autonomy_allows_action(
    mandate: Mapping[str, Any] | None,
    *,
    action_type: str,
    action_payload: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether the mandate permits this action without human approval."""

    policy = normalize_autonomy_mandate(mandate)
    if not policy.get("enabled", True):
        return False

    if action_type in FIRST_TOUCH_ACTION_TYPES:
        return bool(policy.get("auto_send_first_touches", True))

    if action_type in BATCH_CLOSE_ACTION_TYPES:
        return _is_allowed_batch_close(policy, action_payload or {}, context or {})

    return False


def _is_allowed_batch_close(
    mandate: Mapping[str, Any],
    action_payload: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    if not mandate.get("auto_close_batch_packs", True):
        return False

    pack_keys = {
        str(pack.get("pack_key"))
        for pack in mandate.get("allowed_batch_packs", [])
        if isinstance(pack, Mapping) and pack.get("pack_key")
    }
    raw_pack_key = action_payload.get("pack_key") or context.get("pack_key")
    pack_key = str(raw_pack_key) if raw_pack_key is not None else None
    if pack_key is not None and pack_keys and pack_key not in pack_keys:
        return False

    amount_cents = _extract_amount_cents(action_payload, context)
    if amount_cents is None:
        return pack_key is not None
    return amount_cents <= int(mandate.get("batch_pack_max_price_cents", 399_700))


def _extract_amount_cents(
    action_payload: Mapping[str, Any], context: Mapping[str, Any]
) -> int | None:
    raw = (
        action_payload.get("amount_cents")
        or action_payload.get("price_cents")
        or context.get("amount_cents")
        or context.get("price_cents")
    )
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    amount = action_payload.get("amount") or action_payload.get("price") or context.get("amount")
    if amount is None:
        return None
    try:
        return int(round(float(amount) * 100))
    except (TypeError, ValueError):
        return None


def escalation_matches(mandate: Mapping[str, Any] | None, text: str) -> list[dict[str, Any]]:
    """Return mandate escalation rules whose keywords appear in text."""

    policy = normalize_autonomy_mandate(mandate)
    normalized_text = text.lower()
    matches: list[dict[str, Any]] = []
    for rule in policy.get("escalation_rules", []):
        if not isinstance(rule, Mapping):
            continue
        keywords = rule.get("keywords", [])
        if not isinstance(keywords, list):
            continue
        for keyword in keywords:
            if isinstance(keyword, str) and re.search(
                rf"\b{re.escape(keyword.lower())}\b", normalized_text
            ):
                matches.append(dict(rule))
                break
    return matches
