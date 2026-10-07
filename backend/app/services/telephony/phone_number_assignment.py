"""Phone-number agent assignment and inbound voice readiness.

A purchased number advertises provider capabilities (``voice_enabled``), but an
inbound call is only answered by an AI agent when the number's fallback
assignment (``PhoneNumber.assigned_agent_id``) points at an active,
voice-capable agent in the same workspace. Campaign, conversation, and
reason-based routing still take priority in ``VoiceAgentResolver``; this module
only owns the number-level fallback and how ready it is.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.scope import apply_workspace_scope
from app.models.agent import Agent
from app.models.phone_number import PhoneNumber

VOICE_CHANNEL_MODES: frozenset[str] = frozenset({"voice", "both"})

AGENT_CREATE_HREF = "/agents/create"
AGENT_CREATE_LABEL = "Create a voice agent"

InboundVoiceStatus = Literal[
    "ready",
    "needs_agent_choice",
    "no_eligible_agent",
    "agent_not_eligible",
    "voice_disabled",
    "number_inactive",
]

AgentAssignmentSource = Literal["explicit", "default_single_agent", "skipped", "pending"]


class AgentAssignmentError(ValueError):
    """Raised when a requested agent cannot be assigned to a workspace number."""


def is_voice_eligible(agent: Agent) -> bool:
    """Whether an agent can answer inbound calls."""
    return bool(agent.is_active) and agent.channel_mode in VOICE_CHANNEL_MODES


async def list_eligible_voice_agents(db: AsyncSession, workspace_id: uuid.UUID) -> list[Agent]:
    """Return active, voice-capable agents owned by ``workspace_id``."""
    result = await db.execute(
        apply_workspace_scope(select(Agent), Agent, workspace_id)
        .where(
            Agent.is_active.is_(True),
            Agent.channel_mode.in_(sorted(VOICE_CHANNEL_MODES)),
        )
        .order_by(Agent.created_at.asc())
    )
    return list(result.scalars().all())


async def get_assignable_agent(
    db: AsyncSession, workspace_id: uuid.UUID, agent_id: uuid.UUID
) -> Agent:
    """Load an agent that may be assigned to a number in ``workspace_id``.

    The agent must belong to the workspace and be active. Text-only agents are
    allowed so SMS-only numbers keep working; readiness reports them as not
    able to answer calls.

    Raises:
        AgentAssignmentError: The agent is missing, in another workspace, or inactive.
    """
    result = await db.execute(
        apply_workspace_scope(select(Agent), Agent, workspace_id).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentAssignmentError("Agent not found in this workspace")
    if not agent.is_active:
        raise AgentAssignmentError("Agent is inactive; activate it before assigning a number")
    return agent


@dataclass(frozen=True)
class PurchaseAssignmentPlan:
    """Which agent (if any) a newly purchased number should be assigned to."""

    agent_id: uuid.UUID | None
    source: AgentAssignmentSource


async def plan_purchase_assignment(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    requested_agent_id: uuid.UUID | None,
    skip_agent_assignment: bool,
) -> PurchaseAssignmentPlan:
    """Decide the agent assignment before any paid purchase happens.

    - An explicit agent is validated (workspace + active) and used.
    - An explicit skip keeps the number SMS-only/unassigned.
    - Otherwise exactly one eligible voice agent becomes the default; zero or
      several leave the number pending so the operator chooses explicitly.
    """
    if requested_agent_id is not None:
        agent = await get_assignable_agent(db, workspace_id, requested_agent_id)
        return PurchaseAssignmentPlan(agent_id=agent.id, source="explicit")
    if skip_agent_assignment:
        return PurchaseAssignmentPlan(agent_id=None, source="skipped")

    eligible = await list_eligible_voice_agents(db, workspace_id)
    if len(eligible) == 1:
        return PurchaseAssignmentPlan(agent_id=eligible[0].id, source="default_single_agent")
    return PurchaseAssignmentPlan(agent_id=None, source="pending")


@dataclass(frozen=True)
class InboundVoiceReadiness:
    """Whether a number will have an AI agent answer a new inbound call."""

    phone_number_id: uuid.UUID
    status: InboundVoiceStatus
    assigned_agent_id: uuid.UUID | None
    assigned_agent_name: str | None
    eligible_agent_count: int
    message: str
    action_label: str | None = None
    action_href: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def evaluate_inbound_voice_readiness(
    phone: PhoneNumber,
    assigned_agent: Agent | None,
    eligible_agents: Sequence[Agent],
) -> InboundVoiceReadiness:
    """Classify a number's inbound voice readiness.

    ``assigned_agent`` must already be workspace-scoped by the caller; an agent
    from another workspace is treated as not eligible.
    """
    eligible_count = len(eligible_agents)
    workspace_agent = (
        assigned_agent
        if assigned_agent is not None and assigned_agent.workspace_id == phone.workspace_id
        else None
    )

    status: InboundVoiceStatus
    if not phone.is_active:
        status, message = "number_inactive", "This number is inactive and will not answer calls."
    elif not phone.voice_enabled:
        status, message = "voice_disabled", "Voice is turned off for this number (SMS only)."
    elif workspace_agent is not None and is_voice_eligible(workspace_agent):
        status, message = "ready", f"Inbound calls are answered by {workspace_agent.name}."
    elif phone.assigned_agent_id is not None:
        status = "agent_not_eligible"
        message = (
            "The assigned agent cannot answer calls (inactive, text-only, or not in this "
            "workspace). Choose a voice agent."
        )
    elif eligible_count == 0:
        status = "no_eligible_agent"
        message = "No active voice agent exists, so inbound calls go to voicemail."
    else:
        status = "needs_agent_choice"
        message = "No agent is assigned, so inbound calls go to voicemail. Choose a voice agent."

    # With no voice agent to pick, the recovery path is creating one.
    needs_new_agent = status in ("agent_not_eligible", "no_eligible_agent") and not eligible_count
    return InboundVoiceReadiness(
        phone_number_id=phone.id,
        status=status,
        assigned_agent_id=phone.assigned_agent_id,
        assigned_agent_name=workspace_agent.name if workspace_agent is not None else None,
        eligible_agent_count=eligible_count,
        message=message,
        action_label=AGENT_CREATE_LABEL if needs_new_agent else None,
        action_href=AGENT_CREATE_HREF if needs_new_agent else None,
    )


async def get_inbound_voice_readiness(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    phones: Sequence[PhoneNumber],
    eligible_agents: Sequence[Agent] | None = None,
) -> list[InboundVoiceReadiness]:
    """Evaluate readiness for workspace-owned ``phones`` with batched agent lookups."""
    if eligible_agents is None:
        eligible_agents = await list_eligible_voice_agents(db, workspace_id)

    assigned_ids = {p.assigned_agent_id for p in phones if p.assigned_agent_id is not None}
    agents_by_id: dict[uuid.UUID, Agent] = {}
    if assigned_ids:
        result = await db.execute(
            apply_workspace_scope(select(Agent), Agent, workspace_id).where(
                Agent.id.in_(assigned_ids)
            )
        )
        agents_by_id = {agent.id: agent for agent in result.scalars().all()}

    return [
        evaluate_inbound_voice_readiness(
            phone,
            agents_by_id.get(phone.assigned_agent_id) if phone.assigned_agent_id else None,
            eligible_agents,
        )
        for phone in phones
    ]
