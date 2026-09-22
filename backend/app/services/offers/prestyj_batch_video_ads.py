"""Prestyj Batch Video Ads offer ladder source of truth.

The Batch Video Ads product is represented as one Offer row with structured JSONB
metadata, not four linked Offer rows. The packs are choices inside one product and
share one delivery mechanism, checkout flow, and negotiation strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict

PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL = "https://prestyj.com/batch-video-ads"
PRESTYJ_BATCH_VIDEO_ADS_PUBLIC_SLUG = "prestyj-batch-video-ads"


class OfferPack(TypedDict):
    """Queryable pack shape stored in Offer.package_options."""

    key: str
    label: str
    ad_count: int
    price: float
    problems_covered: int
    cost_per_ad: float
    role: str
    recommended: bool
    source_url: str
    notes: NotRequired[str]


class NegotiationStep(TypedDict):
    """Ordered negotiation strategy shape stored in Offer.negotiation_sequence."""

    order: int
    stage: str
    pack_key: str
    action: str
    talk_track: str
    objective: str


class OfferValueStackItem(TypedDict):
    """JSON shape stored in Offer.value_stack_items."""

    name: str
    description: str
    value: float
    included: bool


@dataclass(frozen=True, slots=True)
class PackDefinition:
    """Internal immutable pack definition used to derive stored metadata."""

    key: str
    label: str
    ad_count: int
    price: float
    problems_covered: int
    role: str
    recommended: bool = False
    notes: str | None = None

    @property
    def cost_per_ad(self) -> float:
        """Return rounded cost per produced ad."""
        return round(self.price / self.ad_count, 2)

    def as_offer_pack(self) -> OfferPack:
        """Return this pack in the JSONB shape stored on offers."""
        pack: OfferPack = {
            "key": self.key,
            "label": self.label,
            "ad_count": self.ad_count,
            "price": self.price,
            "problems_covered": self.problems_covered,
            "cost_per_ad": self.cost_per_ad,
            "role": self.role,
            "recommended": self.recommended,
            "source_url": PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL,
        }
        if self.notes:
            pack["notes"] = self.notes
        return pack

    def as_value_stack_item(self) -> OfferValueStackItem:
        """Return this pack in the legacy value-stack shape."""
        return {
            "name": f"{self.ad_count:,} paid video ads",
            "description": (
                f"{self.label} batch covering {self.problems_covered} customer "
                f"problem{'s' if self.problems_covered != 1 else ''}."
            ),
            "value": self.price,
            "included": True,
        }


PRESTYJ_BATCH_VIDEO_ADS_PACK_DEFINITIONS: tuple[PackDefinition, ...] = (
    PackDefinition(
        key="sampler_100",
        label="100 ads",
        ad_count=100,
        price=497.0,
        problems_covered=1,
        role="fallback_sampler",
        notes="Use when the buyer resists the anchor or wants to sample the system first.",
    ),
    PackDefinition(
        key="growth_300",
        label="300 ads",
        ad_count=300,
        price=1497.0,
        problems_covered=3,
        role="mid_pack",
    ),
    PackDefinition(
        key="anchor_500",
        label="500 ads",
        ad_count=500,
        price=2500.0,
        problems_covered=5,
        role="anchor_sweet_spot",
        recommended=True,
        notes="Open here first; this is the anchor and sweet spot for the sales motion.",
    ),
    PackDefinition(
        key="scale_1000",
        label="1,000 ads",
        ad_count=1000,
        price=3997.0,
        problems_covered=10,
        role="upsell_scale",
        notes="Upsell buyers who want the broadest testing matrix and lowest cost per ad.",
    ),
)

PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS: list[OfferPack] = [
    pack.as_offer_pack() for pack in PRESTYJ_BATCH_VIDEO_ADS_PACK_DEFINITIONS
]
PRESTYJ_BATCH_VIDEO_ADS_PACKS_BY_KEY: dict[str, OfferPack] = {
    pack["key"]: pack for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
}


def format_price(price: float) -> str:
    """Format a price without cents for prompt-safe copy."""
    return f"${price:,.0f}"


def _required_pack(pack_key: str) -> OfferPack:
    """Return a configured pack, raising if the canonical ladder is inconsistent."""
    return PRESTYJ_BATCH_VIDEO_ADS_PACKS_BY_KEY[pack_key]


def format_pack_terms() -> str:
    """Return the public pricing ladder copy derived from the canonical packs."""
    return ", ".join(
        f"{pack['label']} for {format_price(pack['price'])}"
        for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
    )


def format_pack_labels() -> str:
    """Return the pack labels as human-readable copy."""
    labels = [pack["label"] for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS]
    return f"{', '.join(labels[:-1])}, or {labels[-1]}" if len(labels) > 1 else labels[0]


def _pack_summary(pack: OfferPack) -> str:
    """Return a concise pack summary derived from the canonical numbers."""
    return (
        f"{pack['label']} for {format_price(pack['price'])} covering "
        f"{pack['problems_covered']} customer problem"
        f"{'s' if pack['problems_covered'] != 1 else ''}"
    )


ENTRY_PACK = PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS[0]
ANCHOR_PACK = _required_pack("anchor_500")
FALLBACK_PACK = _required_pack("sampler_100")
UPSELL_PACK = _required_pack("scale_1000")
PRESTYJ_BATCH_VIDEO_ADS_ENTRY_PRICE = ENTRY_PACK["price"]
PRESTYJ_BATCH_VIDEO_ADS_MAX_PRICE = max(
    pack["price"] for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
)
PRESTYJ_BATCH_VIDEO_ADS_PACK_TERMS = format_pack_terms()
PRESTYJ_BATCH_VIDEO_ADS_PACK_LABELS = format_pack_labels()

PRESTYJ_BATCH_VIDEO_ADS_NEGOTIATION_SEQUENCE: list[NegotiationStep] = [
    {
        "order": 1,
        "stage": "anchor",
        "pack_key": ANCHOR_PACK["key"],
        "action": "lead_with_anchor",
        "talk_track": (
            f"Recommend the {_pack_summary(ANCHOR_PACK)} sweet spot first; it gives enough "
            "volume to test hooks, angles, and CTAs without dragging out production."
        ),
        "objective": f"Make the {ANCHOR_PACK['label']} feel like the default buying decision.",
    },
    {
        "order": 2,
        "stage": "fallback",
        "pack_key": FALLBACK_PACK["key"],
        "action": "offer_sampler_on_resistance",
        "talk_track": (
            f"If they resist budget or volume, fall back to the {_pack_summary(FALLBACK_PACK)} "
            "sampler so they can see the system work with minimal risk."
        ),
        "objective": "Preserve a paid yes instead of over-handling price resistance.",
    },
    {
        "order": 3,
        "stage": "upsell",
        "pack_key": UPSELL_PACK["key"],
        "action": "expand_to_scale_pack",
        "talk_track": (
            "If they want broader testing or ask what finds winners fastest, upsell to "
            f"{_pack_summary(UPSELL_PACK)} and the lowest cost per ad."
        ),
        "objective": "Increase deal size when the buyer shows scale intent.",
    },
    {
        "order": 4,
        "stage": "close",
        "pack_key": ANCHOR_PACK["key"],
        "action": "stripe_checkout_close",
        "talk_track": (
            "Once they choose a pack, confirm the package in one sentence and move directly to "
            "Stripe checkout. After payment, report the sale and selected pack to the operator "
            "by text."
        ),
        "objective": "Convert pack selection into payment without adding a human approval step.",
    },
]

PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA = {
    "source_url": PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL,
    "representation": "single_offer_with_package_options_and_negotiation_sequence",
    "default_anchor_pack_key": "anchor_500",
    "fallback_pack_key": "sampler_100",
    "upsell_pack_key": "scale_1000",
    "autonomy": (
        "Agent may discover, first-touch, objection-handle, close, and report without human "
        "approval."
    ),
    "human_escalation_triggers": [
        "Buyer asks for media buying or running ads",
        "Buyer asks for AI agent installation",
        "Buyer asks for consulting or services beyond the selected batch video ads pack",
    ],
    "not_included": [
        "Media buying",
        "Ad account management",
        "Campaign setup inside Meta, TikTok, or YouTube",
        "Landing page builds",
        "Copywriting outside the ad scripts",
        "Paid actors or studio crew",
        "Long-form or VSL editing",
        "Analytics dashboards",
    ],
}

PRESTYJ_BATCH_VIDEO_ADS_VALUE_STACK_ITEMS: list[OfferValueStackItem] = [
    *(pack.as_value_stack_item() for pack in PRESTYJ_BATCH_VIDEO_ADS_PACK_DEFINITIONS),
    {
        "name": "One recording session",
        "description": (
            "Capture the source material once, then repurpose it into batch ad creative."
        ),
        "value": 0.0,
        "included": True,
    },
    {
        "name": "1-2 business day delivery",
        "description": (
            "Fast turnaround after footage is received and required assets are complete."
        ),
        "value": 0.0,
        "included": True,
    },
]


def get_pack_definition(pack_key: str) -> OfferPack | None:
    """Return a pack definition by key."""
    return next(
        (pack for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS if pack["key"] == pack_key),
        None,
    )
