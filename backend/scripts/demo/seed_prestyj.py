"""Seed a deterministic Prestyj Batch Video Ads demo workspace.

Run from ``backend/``:

    uv run python -m scripts.seed_prestyj

The script is idempotent: it upserts the demo workspace/auth assets, moves the
canonical Batch Video Ads offer into that workspace if necessary, resets the AI
sales agent, iMessage sender, and ad-library contacts to a known state, then
prints the workspace ID and deterministic API key for endpoint verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import textwrap
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import hash_value
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.api_key import APIKey
from app.models.contact import Contact
from app.models.offer import Offer
from app.models.phone_number import (
    PhoneNumber,
    PhoneNumberHealthStatus,
    PhoneNumberProvider,
    TrustTier,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.autonomy_mandate import prestyj_autonomy_mandate
from app.services.offers.prestyj_batch_video_ads import (
    ANCHOR_PACK,
    FALLBACK_PACK,
    PRESTYJ_BATCH_VIDEO_ADS_PACK_TERMS,
    PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS,
    PRESTYJ_BATCH_VIDEO_ADS_PUBLIC_SLUG,
    PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA,
    UPSELL_PACK,
    format_price,
)
from scripts.demo.seed_prestyj_batch_video_ads_offer import (
    PRESTYJ_BATCH_VIDEO_ADS_TEMPLATE,
)

NS = uuid.UUID("d08932c5-e5df-4ae3-9ea1-66e8f625badd")
WORKSPACE_ID = uuid.uuid5(NS, "workspace:prestyj-batch-video-ads-demo")
WORKSPACE_NAME = "Prestyj Batch Video Ads Demo"
WORKSPACE_SLUG = "prestyj-batch-video-ads-demo"
USER_EMAIL = "prestyj-demo@example.com"
USER_PASSWORD = "PrestyjDemo!2026"
API_KEY_NAME = "prestyj-demo-seed"
API_KEY_SECRET = "tt_prestyj_demo_seed_2026"
AGENT_ID = uuid.uuid5(NS, "agent:prestyj-autonomous-imessage-closer")
PHONE_ID = uuid.uuid5(NS, "phone:prestyj-demo-imessage")
PHONE_NUMBER = "+18885550197"
CONTACT_ID_START = 9_970_000
SEED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ContactSpec:
    """Deterministic ad-library advertiser contact seed fields."""

    company_name: str
    first_name: str
    last_name: str
    phone_number: str
    email: str
    website_url: str
    niche: str
    city: str
    state: str
    lead_score: int
    pain_points: tuple[str, ...]


CONTACT_SPECS: tuple[ContactSpec, ...] = (
    ContactSpec(
        "Peak Roofing Pros",
        "Mason",
        "Reed",
        "+14155550100",
        "mason@peakroofingpros.example",
        "https://peakroofingpros.example",
        "Roofing",
        "Austin",
        "TX",
        96,
        ("same storm-damage ad running 210 days", "few visible creative tests"),
    ),
    ContactSpec(
        "BrightPath Dental Studio",
        "Lena",
        "Ortiz",
        "+14155550101",
        "lena@brightpathdental.example",
        "https://brightpathdental.example",
        "Dental implants",
        "Phoenix",
        "AZ",
        92,
        ("high-ticket implant offer", "ad fatigue risk from one testimonial creative"),
    ),
    ContactSpec(
        "Summit HVAC & Air",
        "Grant",
        "Ellis",
        "+14155550102",
        "grant@summithvacair.example",
        "https://summithvacair.example",
        "HVAC",
        "Tampa",
        "FL",
        89,
        ("seasonal tune-up ads need angle variety", "strong local service demand"),
    ),
    ContactSpec(
        "Evergreen Med Spa",
        "Priya",
        "Shah",
        "+14155550103",
        "priya@evergreenmedspa.example",
        "https://evergreenmedspa.example",
        "Med spa",
        "Scottsdale",
        "AZ",
        87,
        ("repeats one Botox promo", "premium buyer likely values fast video volume"),
    ),
    ContactSpec(
        "Atlas Solar Group",
        "Drew",
        "Kim",
        "+14155550104",
        "drew@atlassolargroup.example",
        "https://atlassolargroup.example",
        "Solar installation",
        "San Diego",
        "CA",
        84,
        ("lead-gen ads with stale hooks", "large objections matrix to test"),
    ),
    ContactSpec(
        "ClearView Window Co",
        "Natalie",
        "Brooks",
        "+14155550105",
        "natalie@clearviewwindowco.example",
        "https://clearviewwindowco.example",
        "Windows",
        "Denver",
        "CO",
        82,
        ("offer has not changed in months", "visual before-after angles underused"),
    ),
    ContactSpec(
        "Urban Fit Lab",
        "Cam",
        "Hayes",
        "+14155550106",
        "cam@urbanfitlab.example",
        "https://urbanfitlab.example",
        "Fitness studio",
        "Chicago",
        "IL",
        78,
        ("membership ads are repetitive", "needs local proof and instructor angles"),
    ),
    ContactSpec(
        "Northstar Legal Funding",
        "Avery",
        "Cole",
        "+14155550107",
        "avery@northstarlegalfunding.example",
        "https://northstarlegalfunding.example",
        "Legal funding",
        "Atlanta",
        "GA",
        75,
        ("compliance-heavy offer", "needs many objection-specific scripts"),
    ),
    ContactSpec(
        "Prime Patio Builders",
        "Sofia",
        "Marin",
        "+14155550108",
        "sofia@primepatio.example",
        "https://primepatio.example",
        "Outdoor living",
        "Charlotte",
        "NC",
        73,
        ("seasonal creative window", "project photos need stronger hook testing"),
    ),
    ContactSpec(
        "Bluebird Real Estate Team",
        "Tyler",
        "Nguyen",
        "+14155550109",
        "tyler@bluebirdrealestate.example",
        "https://bluebirdrealestate.example",
        "Real estate",
        "Nashville",
        "TN",
        71,
        ("listing lead magnets repeated", "could test neighborhood-specific video ads"),
    ),
    ContactSpec(
        "Stonebridge Remodelers",
        "Mira",
        "Patel",
        "+14155550110",
        "mira@stonebridgeremodelers.example",
        "https://stonebridgeremodelers.example",
        "Home remodeling",
        "Raleigh",
        "NC",
        69,
        ("high-ticket kitchen offers", "limited creative rotation"),
    ),
    ContactSpec(
        "CloudNine IV Therapy",
        "Jonah",
        "Price",
        "+14155550111",
        "jonah@cloudnineiv.example",
        "https://cloudnineiv.example",
        "IV therapy",
        "Las Vegas",
        "NV",
        66,
        ("wellness benefits need segmented hooks", "same lifestyle visual running long"),
    ),
    ContactSpec(
        "TrueNorth Pest Control",
        "Erin",
        "Walsh",
        "+14155550112",
        "erin@truenorthpest.example",
        "https://truenorthpest.example",
        "Pest control",
        "Orlando",
        "FL",
        63,
        ("routine coupon ads", "seasonal bug-problem angles untested"),
    ),
    ContactSpec(
        "Cedar & Slate Interiors",
        "Noah",
        "Bell",
        "+14155550113",
        "noah@cedarslate.example",
        "https://cedarslate.example",
        "Interior design",
        "Portland",
        "OR",
        60,
        ("premium trust needs more founder video", "portfolio ads lack direct CTAs"),
    ),
    ContactSpec(
        "NovaSmile Orthodontics",
        "Jules",
        "Carter",
        "+14155550114",
        "jules@novasmileortho.example",
        "https://novasmileortho.example",
        "Orthodontics",
        "Columbus",
        "OH",
        58,
        ("clear-aligner ads repeat", "parent and adult buyer angles differ"),
    ),
    ContactSpec(
        "Ironclad Garage Doors",
        "Blake",
        "Stone",
        "+14155550115",
        "blake@ironcladgarage.example",
        "https://ironcladgarage.example",
        "Garage doors",
        "Kansas City",
        "MO",
        55,
        ("emergency repair hooks present", "upgrade and security angles missing"),
    ),
    ContactSpec(
        "Willow Creek Landscaping",
        "Harper",
        "Lane",
        "+14155550116",
        "harper@willowcreeklandscaping.example",
        "https://willowcreeklandscaping.example",
        "Landscaping",
        "Salt Lake City",
        "UT",
        52,
        ("beautiful visuals but few offers", "seasonal package testing needed"),
    ),
    ContactSpec(
        "Metro Hearing Center",
        "Owen",
        "Diaz",
        "+14155550117",
        "owen@metrohearing.example",
        "https://metrohearing.example",
        "Audiology",
        "Minneapolis",
        "MN",
        49,
        ("education-heavy buyer journey", "trust proof could be chunked into videos"),
    ),
    ContactSpec(
        "Copperline Plumbing",
        "Isla",
        "Ford",
        "+14155550118",
        "isla@copperlineplumbing.example",
        "https://copperlineplumbing.example",
        "Plumbing",
        "Dallas",
        "TX",
        46,
        ("service ads are commodity-like", "video could create stronger local trust"),
    ),
    ContactSpec(
        "MarketMuse Boutique",
        "Riley",
        "Chen",
        "+14155550119",
        "riley@marketmuseboutique.example",
        "https://marketmuseboutique.example",
        "Retail boutique",
        "Brooklyn",
        "NY",
        41,
        ("lower-ticket fit", "could use sampler pack if budget resistant"),
    ),
)


def _api_key_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _offer_values(workspace_id: uuid.UUID) -> dict[str, object]:
    return PRESTYJ_BATCH_VIDEO_ADS_TEMPLATE.to_offer_values(workspace_id)


def _agent_prompt() -> str:
    ladder = "; ".join(
        f"{pack['label']}={format_price(float(pack['price']))} ({pack['role']})"
        for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS
    )
    escalation_triggers = "; ".join(
        str(trigger)
        for trigger in PRESTYJ_BATCH_VIDEO_ADS_STRATEGY_METADATA["human_escalation_triggers"]
    )
    anchor_price = format_price(float(ANCHOR_PACK["price"]))
    fallback_price = format_price(float(FALLBACK_PACK["price"]))
    upsell_price = format_price(float(UPSELL_PACK["price"]))
    return textwrap.dedent(
        f"""
        You are Prestyj's autonomous iMessage sales operator for Batch Video Ads.

        Mission: run the full sales motion 24/7 over SMS/iMessage: discover qualified
        advertisers, send first-touch outreach, handle objections, recommend the anchor pack,
        close with Stripe checkout, then text the operator a concise sale report after payment.

        Canonical offer ladder: {ladder}.
        Default close: lead with the {ANCHOR_PACK["label"]} anchor at {anchor_price}; it is
        the sweet spot for enough creative volume to test hooks, angles, and CTAs. If budget
        resistance is real, preserve a paid yes with {FALLBACK_PACK["label"]} at
        {fallback_price}. If they want maximum testing breadth or the lowest cost per ad,
        offer {UPSELL_PACK["label"]} at {upsell_price}.

        Rules:
        - Stay concise, human, confident, and direct. No corporate filler.
        - Use the search_knowledge tool before making factual claims about pricing,
          turnaround, scope, exclusions, Andromeda, UGC creators, or agencies.
        - Never ask a human for approval to sell a standard batch pack.
        - Confirm the selected pack, collect any missing checkout details, create/send the
          Stripe checkout link, and follow up until paid or clearly declined.
        - After payment, report buyer, company, selected pack, price, objections handled, and
          promised next step to the operator by text.
        - Escalate ONLY for add-ons beyond the batch: {escalation_triggers}.
        - Batch Video Ads do not include media buying, installing AI agents, consulting, ad
          account setup, ad spend, landing pages, or ongoing campaign management.
        """
    ).strip()


async def _upsert_user(db: AsyncSession) -> User:
    user = (
        await db.execute(select(User).where(User.email_hash == hash_value(USER_EMAIL)))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=USER_EMAIL,
            email_hash=hash_value(USER_EMAIL),
            hashed_password=get_password_hash(USER_PASSWORD),
            full_name="Prestyj Demo Operator",
            phone_number="+14155551997",
            timezone="America/New_York",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = USER_EMAIL
        user.hashed_password = get_password_hash(USER_PASSWORD)
        user.full_name = "Prestyj Demo Operator"
        user.phone_number = "+14155551997"
        user.timezone = "America/New_York"
        user.is_active = True
    return user


async def _upsert_workspace(db: AsyncSession) -> Workspace:
    workspace = (
        await db.execute(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
    ).scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            id=WORKSPACE_ID,
            name=WORKSPACE_NAME,
            slug=WORKSPACE_SLUG,
            description=(
                "Deterministic demo workspace for autonomous Prestyj Batch Video Ads sales."
            ),
            settings={
                "vertical": "prestyj_batch_video_ads",
                "timezone": "America/New_York",
                "operator_report_phone": "+14155551997",
            },
            autonomy_mandate=prestyj_autonomy_mandate(operator_phone="+14155551997"),
            is_active=True,
        )
        db.add(workspace)
        await db.flush()
    else:
        workspace.name = WORKSPACE_NAME
        workspace.description = (
            "Deterministic demo workspace for autonomous Prestyj Batch Video Ads sales."
        )
        workspace.settings = {
            **(workspace.settings or {}),
            "vertical": "prestyj_batch_video_ads",
            "timezone": "America/New_York",
            "operator_report_phone": "+14155551997",
        }
        workspace.is_active = True
    return workspace


async def _upsert_membership(db: AsyncSession, user: User, workspace: Workspace) -> None:
    membership = (
        await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.workspace_id == workspace.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        db.add(
            WorkspaceMembership(
                user_id=user.id,
                workspace_id=workspace.id,
                role="owner",
                is_default=True,
            )
        )
    else:
        membership.role = "owner"
        membership.is_default = True


async def _upsert_api_key(db: AsyncSession, user: User, workspace: Workspace) -> None:
    key_hash = _api_key_hash(API_KEY_SECRET)
    api_key = (
        await db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    ).scalar_one_or_none()
    if api_key is None:
        db.add(
            APIKey(
                workspace_id=workspace.id,
                user_id=user.id,
                name=API_KEY_NAME,
                key_hash=key_hash,
                key_prefix=API_KEY_SECRET[:8],
                is_active=True,
            )
        )
    else:
        api_key.workspace_id = workspace.id
        api_key.user_id = user.id
        api_key.name = API_KEY_NAME
        api_key.key_prefix = API_KEY_SECRET[:8]
        api_key.is_active = True
        api_key.expires_at = None


async def _reset_offer(db: AsyncSession, workspace: Workspace) -> Offer:
    values = _offer_values(workspace.id)
    offer = (
        await db.execute(
            select(Offer).where(Offer.public_slug == PRESTYJ_BATCH_VIDEO_ADS_PUBLIC_SLUG)
        )
    ).scalar_one_or_none()
    if offer is None:
        offer = Offer(**values)
        db.add(offer)
        await db.flush()
    else:
        for field, value in values.items():
            setattr(offer, field, value)
    return offer


async def _reset_agent(db: AsyncSession, workspace: Workspace) -> Agent:
    agent = await db.get(Agent, AGENT_ID)
    if agent is None:
        agent = (
            await db.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace.id,
                    Agent.name == "Prestyj Autonomous iMessage Closer",
                )
            )
        ).scalar_one_or_none()
    if agent is None:
        agent = Agent(
            id=AGENT_ID, workspace_id=workspace.id, name="Prestyj Autonomous iMessage Closer"
        )
        db.add(agent)

    agent.workspace_id = workspace.id
    agent.name = "Prestyj Autonomous iMessage Closer"
    agent.description = (
        "Fully autonomous text sales agent for Prestyj Batch Video Ads: discover, "
        "first-touch, objection-handle, anchor-close, Stripe checkout, and operator report."
    )
    agent.channel_mode = "text"
    agent.voice_provider = "openai"
    agent.voice_id = "alloy"
    agent.language = "en-US"
    agent.system_prompt = _agent_prompt()
    agent.temperature = 0.55
    agent.max_tokens = 1200
    agent.initial_greeting = (
        "Quick question — are you still running paid social ads for your business?"
    )
    agent.text_response_delay_ms = 5_000
    agent.text_max_context_messages = 30
    agent.enabled_tools = [
        "crm",
        "stripe_checkout",
        "send_sms",
        "operator_text_report",
        "search_knowledge",
    ]
    agent.tool_settings = {
        "crm": ["search_contacts", "update_contact", "record_outcome"],
        "stripe_checkout": ["create_checkout_link", "send_checkout_link"],
        "send_sms": ["mac_relay_imessage"],
        "operator_text_report": ["payment_succeeded"],
        "search_knowledge": {
            "required_for": ["pricing", "delivery", "scope", "exclusions", "objections"]
        },
    }
    agent.embed_settings = {
        "offer_public_slug": PRESTYJ_BATCH_VIDEO_ADS_PUBLIC_SLUG,
        "allowed_pack_keys": [pack["key"] for pack in PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS],
        "default_pack_key": "anchor_500",
        "operator_report_phone": "+14155551997",
        "sms_provider": "mac_relay",
        "sms_service": "imessage",
    }
    agent.is_active = True
    agent.embed_enabled = False
    await db.flush()
    return agent


async def _reset_phone_number(db: AsyncSession, workspace: Workspace, agent: Agent) -> PhoneNumber:
    phone = (
        await db.execute(select(PhoneNumber).where(PhoneNumber.phone_number == PHONE_NUMBER))
    ).scalar_one_or_none()
    if phone is None:
        phone = PhoneNumber(id=PHONE_ID, phone_number=PHONE_NUMBER)
        db.add(phone)
    phone.workspace_id = workspace.id
    phone.friendly_name = "Prestyj Demo iMessage Sender"
    phone.provider = PhoneNumberProvider.MAC_RELAY
    phone.telnyx_phone_number_id = None
    phone.telnyx_messaging_profile_id = None
    phone.mac_relay_sender_id = "prestyj-demo-imessage"
    phone.sms_enabled = True
    phone.voice_enabled = False
    phone.mms_enabled = True
    phone.imessage_enabled = True
    phone.mac_relay_service = "imessage"
    phone.assigned_agent_id = agent.id
    phone.is_active = True
    phone.trust_tier = TrustTier.STANDARD
    phone.daily_limit = 500
    phone.hourly_limit = 80
    phone.messages_per_second = 1.0
    phone.health_status = PhoneNumberHealthStatus.HEALTHY
    phone.delivery_rate = 1.0
    phone.bounce_rate = 0.0
    phone.complaint_rate = 0.0
    await db.flush()
    return phone


def _contact_from_spec(workspace: Workspace, spec: ContactSpec, index: int) -> Contact:
    return Contact(
        id=CONTACT_ID_START + index,
        workspace_id=workspace.id,
        first_name=spec.first_name,
        last_name=spec.last_name,
        email=spec.email,
        phone_number=spec.phone_number,
        company_name=spec.company_name,
        status="new",
        lead_score=spec.lead_score,
        is_qualified=spec.lead_score >= 70,
        qualification_signals={
            "budget": {
                "detected": spec.lead_score >= 60,
                "value": "actively running paid social ads",
                "confidence": min(0.98, round(spec.lead_score / 100, 2)),
            },
            "authority": {"detected": True, "value": "owner/operator", "confidence": 0.72},
            "need": {
                "detected": True,
                "value": "needs more ad creative volume",
                "confidence": 0.86,
            },
            "timeline": {
                "detected": spec.lead_score >= 70,
                "value": "this month",
                "confidence": 0.68,
            },
            "interest_level": "high" if spec.lead_score >= 80 else "medium",
            "pain_points": list(spec.pain_points),
            "objections": ["budget", "does this include running ads"],
            "next_steps": "Outbound iMessage first-touch for Batch Video Ads.",
            "last_analyzed_at": SEED_TIME.isoformat(),
            "conversation_count": 0,
        },
        qualified_at=SEED_TIME if spec.lead_score >= 70 else None,
        notes=(
            f"Seeded ad-library advertiser in {spec.niche}. Pitch Prestyj Batch Video Ads; "
            f"lead with the 500-ad anchor and use the 100-ad sampler only on price resistance."
        ),
        website_url=spec.website_url,
        business_intel={
            "source": "ad_library",
            "niche": spec.niche,
            "location": f"{spec.city}, {spec.state}",
            "observed_ads": {
                "platforms": ["facebook", "instagram"],
                "active_creatives": 2 + (spec.lead_score % 4),
                "longest_running_days": 45 + spec.lead_score,
                "creative_refresh_rate": round((100 - spec.lead_score) / 100, 2),
            },
            "recommended_pack_key": "anchor_500" if spec.lead_score >= 55 else "sampler_100",
        },
        enrichment_status="enriched",
        enriched_at=SEED_TIME,
        source="ad_library",
        sms_consent_status="unknown",
        sms_consent_source="ad_library_demo_seed",
        engagement_score=max(0, spec.lead_score - 30),
        created_at=SEED_TIME,
        updated_at=SEED_TIME,
    )


async def _reset_contacts(db: AsyncSession, workspace: Workspace) -> list[Contact]:
    await db.execute(
        delete(Contact).where(Contact.workspace_id == workspace.id, Contact.source == "ad_library")
    )
    contacts = [
        _contact_from_spec(workspace, spec, index)
        for index, spec in enumerate(CONTACT_SPECS, start=1)
    ]
    db.add_all(contacts)
    await db.flush()
    return contacts


def _assert_ladder(packs: Iterable[dict[str, Any]]) -> None:
    actual = [(int(pack["ad_count"]), float(pack["price"])) for pack in packs]
    expected = [(100, 497.0), (300, 1497.0), (500, 2500.0), (1000, 3997.0)]
    if actual != expected:
        msg = f"Canonical Prestyj Batch Video Ads ladder changed unexpectedly: {actual}"
        raise RuntimeError(msg)


async def seed() -> tuple[Workspace, Offer, Agent, PhoneNumber, list[Contact]]:
    """Reset the Prestyj demo workspace to the deterministic seeded state."""
    _assert_ladder(PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS)
    async with AsyncSessionLocal() as db:
        user = await _upsert_user(db)
        workspace = await _upsert_workspace(db)
        await _upsert_membership(db, user, workspace)
        await _upsert_api_key(db, user, workspace)
        offer = await _reset_offer(db, workspace)
        workspace.autonomy_mandate = prestyj_autonomy_mandate(
            offer_id=str(offer.id), operator_phone="+14155551997"
        )
        agent = await _reset_agent(db, workspace)
        phone = await _reset_phone_number(db, workspace, agent)
        contacts = await _reset_contacts(db, workspace)
        await db.commit()
        await db.refresh(workspace)
        await db.refresh(offer)
        await db.refresh(agent)
        await db.refresh(phone)
        return workspace, offer, agent, phone, contacts


def main() -> None:
    workspace, offer, agent, phone, contacts = asyncio.run(seed())
    print("Seeded Prestyj Batch Video Ads demo workspace")
    print(f"  workspace_id={workspace.id}")
    print(f"  workspace_slug={workspace.slug}")
    print(f"  offer_id={offer.id}")
    print(f"  offer_ladder={PRESTYJ_BATCH_VIDEO_ADS_PACK_TERMS}")
    print(f"  agent_id={agent.id}")
    print(f"  phone_number={phone.phone_number} provider={phone.provider.value}")
    print(f"  ad_library_contacts={len(contacts)}")
    print(f"  api_key={API_KEY_SECRET}")


if __name__ == "__main__":
    main()
