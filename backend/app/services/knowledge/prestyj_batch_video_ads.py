"""Seedable Prestyj Batch Video Ads knowledge-base documents.

The sales agent should retrieve these facts with ``search_knowledge`` before making
claims about pricing, delivery, scope, exclusions, or competitive positioning.
The wording is intentionally compact and source-cited so the RAG chunks stay
factual and easy to verify.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.offers.prestyj_batch_video_ads import (
    PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS,
    PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL,
    format_price,
)

KNOWLEDGE_SEED_KEY_PREFIX = "prestyj_batch_video_ads"
KNOWLEDGE_SEED_VERSION = "2026-06-14"


@dataclass(frozen=True, slots=True)
class KnowledgeSeedDocument:
    """One reproducible knowledge document to upsert for a specific agent."""

    key: str
    title: str
    doc_type: str
    priority: int
    content: str


@dataclass(frozen=True, slots=True)
class RetrievalCheck:
    """A sample objection/query and the facts retrieval must surface."""

    query: str
    expected_terms: tuple[str, ...]


def _money(value: float) -> str:
    """Format dollars with cents for per-ad math."""

    return f"${value:,.2f}"


def _pack_lines() -> list[str]:
    return [
        (
            f"- {pack['label']}: {format_price(float(pack['price']))} total for "
            f"{pack['ad_count']:,} ads = {_money(float(pack['cost_per_ad']))} per ad; "
            f"covers {pack['problems_covered']} customer problem"
            f"{'s' if int(pack['problems_covered']) != 1 else ''}."
        )
        for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
    ]


def _pricing_content() -> str:
    pack_lines = "\n".join(_pack_lines())
    return f"""Source: {PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL}

Canonical offer ladder and cost-per-ad math:
{pack_lines}

Sales motion: lead with the 500 ads pack as the anchor / sweet spot. Use the
100 ads pack only as a sampler or fallback when budget resistance is real. Offer
1,000 ads when the buyer wants the broadest testing matrix and the lowest cost
per ad. The four pack prices are one-time payments; do not invent subscriptions,
retainers, platform fees, usage fees, rush fees, or hidden fees.

The pack size also sets customer-problem coverage: 100 ads tests 1 customer
problem, 300 ads tests 3, 500 ads tests 5, and 1,000 ads tests 10."""


def _scope_content() -> str:
    return f"""Source: {PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL}

Delivery and included scope:
- Delivery is 1–2 business days from the moment Prestyj receives the buyer's
  footage.
- The buyer pays once, then uses the guided filming portal.
- The portal asks quick questions, generates the master script, provides the
  built-in teleprompter, and accepts the raw upload.
- Input needed: one selfie-style 15–20 minute recording / one recording session.
- Prestyj writes the ad scripts for the batch, edits the single recording into
  the selected number of variations, and ships finished vertical ad files.
- Finished files are 9:16, captioned, and ready to upload to Meta, TikTok, and
  YouTube Shorts.
- Revisions are for errors only; this is volume creative testing, not boutique
  taste-based edit work.

Do not promise same-day delivery, guaranteed ROAS, guaranteed appointments,
CTRs, ad-spend performance, or custom production beyond the selected batch."""


def _exclusions_content() -> str:
    return f"""Source: {PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL}

What is NOT included — say this explicitly when asked:
- No media buying.
- No ad-account management.
- No campaign setup inside Meta, TikTok, or YouTube.
- No ad spend.
- No landing page builds.
- No copywriting outside the ad scripts included with the batch.
- No paid actors or studio crew.
- No long-form / VSL editing.
- No analytics dashboards.
- No AI-agent install.
- No consulting or ongoing campaign management.

Escalate ONLY when the buyer wants add-ons beyond the batch: running ads / media
buying, installing AI agents, consulting, ad-account management, landing pages,
or other custom services. Standard batch-pack questions, objections, checkout,
and payment do not need human approval."""


def _andromeda_content() -> str:
    return f"""Source: {PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL}

Andromeda / volume-as-targeting argument:
Meta's Andromeda-era ad delivery rewards broad creative volume. The old playbook
was one hero ad plus narrow lookalikes or interest stacks; the new floor is
creative volume because creative is the targeting input. Batch Video Ads creates
many hooks, problems, CTAs, and angles so the algorithm can find the pockets of
attention instead of forcing the buyer to guess one polished winner.

Use this objection answer: "Hook testing alone can need 50+ variations. If you
make one ad a day, it can take months to learn which hook gets people to stop. A
batch lets you test angles in parallel and find what works in days, not months."

Position volume as practical risk reduction: buyers are not paying for prettier
ads; they are buying enough shots on goal to discover which customer problems,
hooks, and CTAs make the phone ring."""


def _competitive_content() -> str:
    return f"""Source: {PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL}

Objection: "Why not just hire a UGC creator?"
Answer: A UGC creator is one person filming themselves, usually a few ads weeks
later. Prestyj uses the buyer's face or founder's face, writes every script for
the buyer, and delivers 300–1,000 ads in 1–2 business days when they choose a
larger pack. UGC can be useful for a few polished pieces; Batch Video Ads is a
creative system built for the volume modern paid platforms require.

Objection: "Why not use a creative agency?"
Answer: Agencies commonly sell retainers and ship a small number of polished ads
over weeks. Prestyj sells one-time batch packs, ships in 1–2 business days after
footage is received, and keeps cost per ad around $4–$5. The agency model was
built for a world where one polished hero ad could run for months; Batch Video
Ads is built for fast creative testing when ads fatigue quickly.

Objection: "Polished production should work better."
Answer: People can spot a produced ad in half a second and scroll. A casual
selfie-style vertical video looks like content in the feed, so the message earns
attention before it feels like an ad. The buyer is still paying to reach an
audience; the format helps the pitch actually land.

Objection: "What results should I expect?"
Answer: Promise data and creative learning, not performance guarantees. The buyer
gets hundreds of angles to see which customer problems convert, which hooks hold
attention, and which CTAs close. Do not promise CTR, ROAS, appointments, or
revenue because those depend on the offer, audience, media buying, and spend."""


PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS: tuple[KnowledgeSeedDocument, ...] = (
    KnowledgeSeedDocument(
        key=f"{KNOWLEDGE_SEED_KEY_PREFIX}:pricing",
        title="Prestyj Batch Video Ads — Pricing and Pack Math",
        doc_type="pricing",
        priority=100,
        content=_pricing_content(),
    ),
    KnowledgeSeedDocument(
        key=f"{KNOWLEDGE_SEED_KEY_PREFIX}:delivery_scope",
        title="Prestyj Batch Video Ads — Delivery and Included Scope",
        doc_type="policy",
        priority=95,
        content=_scope_content(),
    ),
    KnowledgeSeedDocument(
        key=f"{KNOWLEDGE_SEED_KEY_PREFIX}:exclusions_escalation",
        title="Prestyj Batch Video Ads — Exclusions and Escalation Cases",
        doc_type="policy",
        priority=95,
        content=_exclusions_content(),
    ),
    KnowledgeSeedDocument(
        key=f"{KNOWLEDGE_SEED_KEY_PREFIX}:andromeda_volume",
        title="Prestyj Batch Video Ads — Andromeda and Volume as Targeting",
        doc_type="playbook",
        priority=90,
        content=_andromeda_content(),
    ),
    KnowledgeSeedDocument(
        key=f"{KNOWLEDGE_SEED_KEY_PREFIX}:objections_competitors",
        title="Prestyj Batch Video Ads — UGC and Agency Objection Handling",
        doc_type="faq",
        priority=90,
        content=_competitive_content(),
    ),
)

PRESTYJ_BATCH_VIDEO_ADS_RETRIEVAL_CHECKS: tuple[RetrievalCheck, ...] = (
    RetrievalCheck(
        query="How much is the 500 ad pack and what is the cost per ad?",
        expected_terms=("500 ads", "$2,500", "$5.00 per ad", "anchor"),
    ),
    RetrievalCheck(
        query="Does this include running my ads, media buying, or installing an AI agent?",
        expected_terms=("No media buying", "No ad-account management", "No AI-agent install"),
    ),
    RetrievalCheck(
        query="How fast do I get the files and what exactly is included?",
        expected_terms=("1–2 business days", "teleprompter", "9:16, captioned"),
    ),
    RetrievalCheck(
        query="Why do I need so many variations after Andromeda?",
        expected_terms=("Andromeda", "creative volume", "creative is the targeting input"),
    ),
    RetrievalCheck(
        query="Why not just hire UGC creators or a creative agency?",
        expected_terms=("UGC creator", "creative system", "Agencies", "$4–$5"),
    ),
)


def all_seed_text() -> str:
    """Return all seed document content concatenated for cheap invariant tests."""

    return "\n\n".join(document.content for document in PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS)
