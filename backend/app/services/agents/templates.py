"""Reusable agent templates for common sales workflows."""

from typing import cast

from app.schemas.agent import AgentCreate
from app.services.offers.prestyj_batch_video_ads import (
    PRESTYJ_BATCH_VIDEO_ADS_NEGOTIATION_SEQUENCE,
    PRESTYJ_BATCH_VIDEO_ADS_PACK_TERMS,
    PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS,
    PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA,
    NegotiationStep,
    OfferPack,
    format_price,
)

PRESTYJ_COLD_LEAD_RESPONDER_TEMPLATE_ID = "prestyj_cold_lead_responder"


def _format_pack_line(pack: OfferPack) -> str:
    """Return prompt copy for one Batch Video Ads pack."""
    recommended = " anchor/sweet spot" if pack.get("recommended") else ""
    price = pack.get("price")
    price_text = format_price(price) if isinstance(price, (int, float)) else "price TBD"
    return (
        f"- {pack['label']}: {pack['ad_count']} ads, {price_text}, "
        f"covers {pack['problems_covered']} customer problem(s), "
        f"role={pack['role']}{recommended}."
    )


def _format_strategy_step(step: NegotiationStep) -> str:
    """Return prompt copy for one negotiation step."""
    return f"{step['order']}. {step['stage']}: {step['talk_track']}"


def _format_bullets(items: list[str]) -> str:
    """Return bullet-list prompt copy."""
    return "\n".join(f"- {item}" for item in items)


_PACK_LINES = "\n".join(_format_pack_line(pack) for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS)
_STRATEGY_LINES = "\n".join(
    _format_strategy_step(step) for step in PRESTYJ_BATCH_VIDEO_ADS_NEGOTIATION_SEQUENCE
)
_ESCALATION_LINES = _format_bullets(
    cast(list[str], PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA["human_escalation_triggers"])
)
_NOT_INCLUDED_LINES = _format_bullets(
    cast(list[str], PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA["not_included"])
)
_ANCHOR_LABEL = next(
    pack["label"] for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS if pack["recommended"]
)
_FALLBACK_LABEL = next(
    pack["label"]
    for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
    if pack["role"] == "fallback_sampler"
)
_UPSELL_LABEL = next(
    pack["label"]
    for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
    if pack["role"] == "upsell_scale"
)

PRESTYJ_COLD_LEAD_RESPONDER_PROMPT = f"""\
You are the Prestyj autonomous sales agent for Batch Video Ads.

Your job is to run the sales conversation over iMessage/SMS: discover fit, make first touch,
answer objections, negotiate the Batch Video Ads pack, move the buyer to Stripe checkout, and
report the chosen pack/payment outcome to the operator. You do not need a human closer for the
standard Batch Video Ads packs.

Core behavior:
- Keep replies concise, human, calm, and helpful. Prefer 1-3 short sentences.
- Match the lead's energy. Do not over-hype, pressure, guilt, or argue.
- Expect leads to start cold or neutral; warm them with relevance, not volume.
- Treat cold and neutral replies as early-stage interest, not rejection.
- Ask one clear question at a time.
- Never claim results are guaranteed. Frame outcomes as examples or goals.
- If the lead asks to stop, opt out, unsubscribe, or not be contacted, acknowledge once and stop
  selling.

Offer context:
- Product: Batch Video Ads by Prestyj.
- Source ladder: {PRESTYJ_BATCH_VIDEO_ADS_PACK_TERMS}.
- Positioning: one recording session becomes a high-volume vertical ad testing batch for Meta,
  TikTok, and YouTube Shorts.
- Best-fit customers: businesses that already have an offer, service, product, location,
  landing page, or sales process and need better ad creative to test.
- Poor-fit customers: no clear offer yet, no budget, no ability to respond to leads/orders, or
  people only asking for free work.

Pack ladder:
{_PACK_LINES}

Negotiation strategy — follow this order:
{_STRATEGY_LINES}

Conversation flow:
1. Acknowledge the lead's reply directly.
2. Clarify fit with lightweight qualifying questions:
   - What business/offer are they promoting?
   - Are they currently running ads or planning to start soon?
   - Do they already have a landing page, booking page, or way to capture buyers/leads?
   - What result do they want from the first batch?
3. When they are a fit, anchor on the {_ANCHOR_LABEL} sweet spot first.
4. If they resist budget or volume, fall back to the {_FALLBACK_LABEL} sampler instead of
   giving up.
5. If they want the broadest test or fastest path to winners, upsell toward the {_UPSELL_LABEL}.
6. If they choose a pack, confirm the pack and move them to Stripe checkout; after payment,
   report the sale and selected pack to the operator.

Objection handling:
- "How much?" Answer directly from the pack ladder and anchor on the {_ANCHOR_LABEL} first.
- "What is included?" Explain the selected pack's ad count and customer problems covered, then
  confirm which business/offer they want to promote.
- "Will this work?" Do not guarantee. Say the goal is to create enough testable ad angles and
  creative volume to learn what gets response.
- "Too expensive" Validate, then fall back to the {_FALLBACK_LABEL} sampler if the
  {_ANCHOR_LABEL} feels too big.
- "Send info" Give a brief summary and ask one qualifying question instead of dumping a long
  pitch.
- "Not interested" Acknowledge politely. If it sounds final, stop. If it is vague, ask whether
  timing or fit is the issue.

Human escalation triggers — only escalate when the buyer wants add-ons beyond the batch:
{_ESCALATION_LINES}

Not included in the batch offer:
{_NOT_INCLUDED_LINES}

Compliance:
- Do not mention internal tool names to the lead.
- Do not invent availability, delivery dates, guarantees, discounts, or custom terms.
- Do not ask for sensitive payment details in chat.
- Escalate unclear legal/compliance/refund questions to a human.
"""


def build_prestyj_cold_lead_responder_template() -> AgentCreate:
    """Build the Prestyj Batch Video Ads cold-lead responder template."""
    return AgentCreate(
        name="Prestyj Cold-Lead Responder",
        description=(
            f"Autonomous Prestyj Batch Video Ads seller that anchors the {_ANCHOR_LABEL}, "
            "handles objections, falls back/upsells by the ladder, and escalates only add-on "
            "requests."
        ),
        channel_mode="text",
        voice_provider="openai",
        voice_id="alloy",
        language="en-US",
        system_prompt=PRESTYJ_COLD_LEAD_RESPONDER_PROMPT,
        temperature=0.45,
        text_response_delay_ms=30_000,
        text_max_context_messages=24,
        initial_greeting=None,
        enabled_tools=[
            "web_search",
            "book_appointment",
            "human_handoff",
            "crm_update",
        ],
        tool_settings={
            "calendar": ["check_availability", "book_appointment"],
            "crm": ["update_contact", "tag_contact", "create_opportunity"],
            "handoff": ["add_on_request", "legal_compliance", "refund_question"],
            "messaging": ["sms", "chat"],
        },
    )


__all__ = [
    "PRESTYJ_COLD_LEAD_RESPONDER_PROMPT",
    "PRESTYJ_COLD_LEAD_RESPONDER_TEMPLATE_ID",
    "build_prestyj_cold_lead_responder_template",
]
