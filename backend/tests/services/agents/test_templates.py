"""Tests for reusable agent templates."""

from app.schemas.agent import AgentCreate
from app.services.agents import (
    PRESTYJ_COLD_LEAD_RESPONDER_PROMPT,
    PRESTYJ_COLD_LEAD_RESPONDER_TEMPLATE_ID,
    build_prestyj_cold_lead_responder_template,
)
from app.services.offers.prestyj_batch_video_ads import (
    PRESTYJ_BATCH_VIDEO_ADS_NEGOTIATION_SEQUENCE,
    PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS,
)


def test_prestyj_template_builds_agent_create_payload() -> None:
    """Template should return an AgentCreate-compatible payload."""
    template = build_prestyj_cold_lead_responder_template()

    assert isinstance(template, AgentCreate)
    assert PRESTYJ_COLD_LEAD_RESPONDER_TEMPLATE_ID == "prestyj_cold_lead_responder"
    assert template.name == "Prestyj Cold-Lead Responder"
    assert template.channel_mode == "text"
    assert template.temperature == 0.45
    assert template.text_response_delay_ms == 30_000
    assert template.text_max_context_messages == 24


def test_prestyj_template_prompt_covers_required_sales_workflow() -> None:
    """Prompt should cover autonomous ladder sales workflow and escalation limits."""
    template = build_prestyj_cold_lead_responder_template()
    prompt = template.system_prompt

    normalized_prompt = " ".join(prompt.split())
    anchor_pack = next(
        pack for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS if pack["recommended"]
    )
    fallback_pack = next(
        pack
        for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
        if pack["role"] == "fallback_sampler"
    )
    upsell_pack = next(
        pack for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS if pack["role"] == "upsell_scale"
    )
    required_phrases = [
        "Batch Video Ads",
        "cold or neutral",
        "Pack ladder",
        f"{anchor_pack['label']}: {anchor_pack['ad_count']} ads",
        f"anchor on the {anchor_pack['label']} sweet spot first",
        f"fall back to the {fallback_pack['label']} sampler",
        f"upsell toward the {upsell_pack['label']}",
        "move them to Stripe checkout",
        (
            "Human escalation triggers — only escalate when the buyer wants add-ons "
            "beyond the batch"
        ),
        "Do not guarantee",
        "stop selling",
    ]

    for phrase in required_phrases:
        assert phrase in normalized_prompt

    assert prompt == PRESTYJ_COLD_LEAD_RESPONDER_PROMPT
    assert [step["stage"] for step in PRESTYJ_BATCH_VIDEO_ADS_NEGOTIATION_SEQUENCE] == [
        "anchor",
        "fallback",
        "upsell",
        "close",
    ]


def test_prestyj_template_enables_expected_tools_and_settings() -> None:
    """Template should enable tools in fields already used by the Agent model."""
    template = build_prestyj_cold_lead_responder_template()

    assert template.enabled_tools == [
        "web_search",
        "book_appointment",
        "human_handoff",
        "crm_update",
    ]
    assert template.tool_settings == {
        "calendar": ["check_availability", "book_appointment"],
        "crm": ["update_contact", "tag_contact", "create_opportunity"],
        "handoff": ["add_on_request", "legal_compliance", "refund_question"],
        "messaging": ["sms", "chat"],
    }
