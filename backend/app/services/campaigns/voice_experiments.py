"""Stable, equal-weight voice assignment and campaign booking conversion reports."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.campaign import Campaign, CampaignContact
from app.models.conversation import Message
from app.schemas.voice_experiment import (
    VoiceExperiment,
    VoiceExperimentResults,
    VoiceVariant,
    VoiceVariantResult,
)


def validate_provider(experiment: VoiceExperiment, provider: str) -> None:
    """Reject silent provider voice fallbacks; catalog traits are operator labels."""
    from app.services.ai.codex_app_server import SUPPORTED_CODEX_VOICES
    from app.services.ai.grok.constants import GROK_VOICES
    from app.services.ai.openai_realtime_config import OPENAI_REALTIME_VOICES

    if experiment.provider != provider:
        raise ValueError("Experiment provider must match the campaign voice agent")
    catalogs = {
        "openai": OPENAI_REALTIME_VOICES,
        "grok": frozenset(GROK_VOICES),
        "live": SUPPORTED_CODEX_VOICES,
    }
    if provider == "elevenlabs":
        return  # Account-specific IDs cannot be enumerated locally.
    if provider not in catalogs:
        raise ValueError("Voice experiments require a supported voice provider")
    for variant in experiment.variants:
        if variant.voice_id.lower() not in catalogs[provider]:
            raise ValueError(f"Unsupported {provider} voice: {variant.voice_id}")


def assign_voice(campaign: Campaign, entry: CampaignContact) -> dict[str, Any] | None:
    """Called under the worker's contact row lock, before the dial write.

    Hash campaign + contact IDs, not attempt/order/demographics. Retries and
    re-enrollment in the same campaign get the same arm. Never alter an assignment.
    """
    if entry.voice_assignment:
        return dict(entry.voice_assignment)
    if not campaign.voice_experiment:
        return None
    experiment = VoiceExperiment.model_validate(campaign.voice_experiment)
    agent = campaign.voice_agent
    if agent is None:
        raise ValueError("Voice experiment requires a voice agent")
    validate_provider(experiment, agent.voice_provider)
    digest = hashlib.sha256(f"{campaign.id}:{entry.contact_id}".encode()).digest()
    variant = experiment.variants[int.from_bytes(digest[:8], "big") % len(experiment.variants)]
    assignment: dict[str, Any] = {
        "variant": variant.model_dump(),
        "provider": agent.voice_provider,
        "assigned_at": datetime.now(UTC).isoformat(),
    }
    entry.voice_assignment = assignment
    return assignment


def apply_voice_assignment(agent: Agent, assignment: dict[str, Any]) -> None:
    """Apply only to a detached call-local agent, never persist catalog overrides."""
    from sqlalchemy import inspect

    if inspect(agent).persistent:
        raise ValueError("Voice overrides require a detached agent")
    variant = VoiceVariant.model_validate(assignment["variant"])
    provider = assignment["provider"]
    agent.voice_provider = provider
    agent.voice_id = variant.voice_id if provider == "elevenlabs" else variant.voice_id.lower()
    agent.tool_settings = {
        **(agent.tool_settings or {}),
        "campaign_voice": {"speed": variant.speed, "accent": variant.accent},
    }


async def load_call_voice_assignment(
    db: AsyncSession, agent: Agent | None, message: Message
) -> None:
    """Load an authorized snapshot and detach before changing shared agent settings."""
    if agent is None or message.direction != "outbound" or not message.campaign_id:
        return
    conversation = message.conversation
    result = await db.execute(
        select(CampaignContact.voice_assignment)
        .join(Campaign, Campaign.id == CampaignContact.campaign_id)
        .where(
            Campaign.id == message.campaign_id,
            Campaign.workspace_id == conversation.workspace_id,
            CampaignContact.contact_id == conversation.contact_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment:
        db.expunge(agent)
        apply_voice_assignment(agent, assignment)


async def voice_results(db: AsyncSession, campaign: Campaign) -> VoiceExperimentResults | None:
    """Count each assigned contact once, including failed dials (intent-to-treat).

    Conversion is any campaign-attributed appointment created after assignment,
    including SMS fallback bookings. Cancellations remain historical bookings.
    No unrelated, earlier, or cross-workspace appointment can count.
    """
    if not campaign.voice_experiment:
        return None
    experiment = VoiceExperiment.model_validate(campaign.voice_experiment)
    variant_id = CampaignContact.voice_assignment["variant"]["id"].astext
    assigned_at = cast(
        CampaignContact.voice_assignment["assigned_at"].astext, DateTime(timezone=True)
    )
    converted = (
        select(Appointment.id)
        .where(
            Appointment.workspace_id == campaign.workspace_id,
            Appointment.campaign_id == campaign.id,
            Appointment.contact_id == CampaignContact.contact_id,
            Appointment.created_at >= assigned_at,
        )
        .exists()
    )
    rows = await db.execute(
        select(
            variant_id,
            func.count(CampaignContact.id),
            func.count(CampaignContact.id).filter(converted),
        )
        .where(
            CampaignContact.campaign_id == campaign.id,
            CampaignContact.voice_assignment.is_not(None),
        )
        .group_by(variant_id)
    )
    counts = {arm: (assigned, booked) for arm, assigned, booked in rows}
    results = []
    for variant in experiment.variants:
        assigned, booked = counts.get(variant.id, (0, 0))
        results.append(
            VoiceVariantResult(
                variant=variant,
                assigned_contacts=assigned,
                converted_contacts=booked,
                conversion_rate=100 * booked / assigned if assigned else 0.0,
            )
        )
    return VoiceExperimentResults(variants=results)
