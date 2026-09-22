"""Tests for the workspace autonomy mandate policy object."""

from __future__ import annotations

from app.services.autonomy_mandate import (
    AUTONOMY_MANDATE_VERSION,
    autonomy_allows_action,
    default_autonomy_mandate,
    escalation_matches,
    normalize_autonomy_mandate,
    prestyj_autonomy_mandate,
)


def test_default_mandate_is_act_and_report() -> None:
    mandate = default_autonomy_mandate()

    assert mandate["enabled"] is True
    assert mandate["posture"] == "act_and_report"
    assert mandate["auto_send_first_touches"] is True
    assert mandate["auto_close_batch_packs"] is True
    pack_keys = {pack["pack_key"] for pack in mandate["allowed_batch_packs"]}
    assert pack_keys == {"sampler_100", "growth_300", "anchor_500", "scale_1000"}


def test_normalize_clamps_and_fills_defaults() -> None:
    mandate = normalize_autonomy_mandate(
        {
            "daily_send_cap": 10_000_000,
            "batch_pack_max_price_cents": -5,
            "quiet_hours": "nonsense",
            "escalation_rules": "nonsense",
        }
    )

    assert mandate["version"] == AUTONOMY_MANDATE_VERSION
    assert mandate["daily_send_cap"] == 10_000
    assert mandate["batch_pack_max_price_cents"] == 0
    assert isinstance(mandate["quiet_hours"], dict)
    assert isinstance(mandate["escalation_rules"], list)


def test_normalize_none_returns_default() -> None:
    assert normalize_autonomy_mandate(None) == default_autonomy_mandate()


def test_first_touch_allowed_when_enabled() -> None:
    mandate = default_autonomy_mandate()

    assert autonomy_allows_action(mandate, action_type="outbound.launch_campaign") is True
    assert (
        autonomy_allows_action(
            mandate, action_type="crm_assistant.send_initial_message"
        )
        is True
    )


def test_first_touch_blocked_when_disabled() -> None:
    mandate = default_autonomy_mandate()
    mandate["auto_send_first_touches"] = False

    assert autonomy_allows_action(mandate, action_type="outbound.launch_campaign") is False


def test_disabled_mandate_blocks_everything() -> None:
    mandate = default_autonomy_mandate()
    mandate["enabled"] = False

    assert autonomy_allows_action(mandate, action_type="outbound.launch_campaign") is False
    assert (
        autonomy_allows_action(
            mandate,
            action_type="stripe_checkout.create_checkout_link",
            action_payload={"pack_key": "anchor_500", "amount_cents": 250_000},
        )
        is False
    )


def test_batch_close_allowed_up_to_anchor_and_1000() -> None:
    mandate = default_autonomy_mandate()

    for pack_key, amount in [("anchor_500", 250_000), ("scale_1000", 399_700)]:
        assert (
            autonomy_allows_action(
                mandate,
                action_type="stripe_checkout.create_checkout_link",
                action_payload={"pack_key": pack_key, "amount_cents": amount},
            )
            is True
        ), pack_key


def test_batch_close_blocked_above_max_price() -> None:
    mandate = default_autonomy_mandate()

    assert (
        autonomy_allows_action(
            mandate,
            action_type="stripe_checkout.create_checkout_link",
            action_payload={"pack_key": "anchor_500", "amount_cents": 999_999},
        )
        is False
    )


def test_batch_close_blocked_for_unknown_pack() -> None:
    mandate = default_autonomy_mandate()

    assert (
        autonomy_allows_action(
            mandate,
            action_type="stripe_checkout.send_checkout_link",
            action_payload={"pack_key": "enterprise_5000"},
        )
        is False
    )


def test_addon_action_types_escalate_by_default() -> None:
    """Add-ons (run ads / agent install / consulting) are never auto-approved."""
    mandate = default_autonomy_mandate()

    for action_type in (
        "crm_assistant.create_agent",
        "crm_assistant.assign_ai_responder",
        "some.unknown.action",
    ):
        assert autonomy_allows_action(mandate, action_type=action_type) is False, action_type


def test_escalation_keywords_match_buyer_addon_requests() -> None:
    mandate = default_autonomy_mandate()

    ad_mgmt = escalation_matches(mandate, "Can you run ads for me too?")
    assert [rule["key"] for rule in ad_mgmt] == ["ad_management"]

    agent = escalation_matches(mandate, "I also want you to install AI for my team")
    assert [rule["key"] for rule in agent] == ["ai_agent_install"]

    consulting = escalation_matches(mandate, "Do you offer consulting?")
    assert [rule["key"] for rule in consulting] == ["consulting"]


def test_escalation_no_match_for_plain_buy_intent() -> None:
    mandate = default_autonomy_mandate()

    assert escalation_matches(mandate, "I'll take the 500 pack, send me the link") == []


def test_prestyj_mandate_carries_offer_and_operator_phone() -> None:
    mandate = prestyj_autonomy_mandate(offer_id="abc", operator_phone="+14155551997")

    assert mandate["default_offer_id"] == "abc"
    assert mandate["operator_report"]["phone"] == "+14155551997"
    assert "description" in mandate
