"""Single model-selection policy: agent override, workspace override, task default.

Pricing is optional; unknown prices are logged as null, never silently treated as zero.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.model_config import ModelConfig
from app.services.ai.openai_realtime_config import normalize_realtime_model

Task = Literal[
    "voice_llm",
    "transcript_analysis",
    "transcript_judgment",
    "caller_memory",
    "prompt_improvement",
    "reports",
]


@dataclass(frozen=True)
class Selection:
    model: str
    input_usd_per_million: Decimal | None = None
    output_usd_per_million: Decimal | None = None


DEFAULTS: dict[Task, str] = {
    "voice_llm": settings.openai_realtime_model,
    "transcript_analysis": settings.transcript_analysis_model,
    "transcript_judgment": settings.transcript_judgment_model,
    "caller_memory": settings.caller_memory_model,
    "prompt_improvement": settings.prompt_improvement_model,
    "reports": settings.reports_model,
}


async def resolve_model(
    db: AsyncSession, task: Task, workspace_id: uuid.UUID, agent_id: uuid.UUID | None = None
) -> Selection:
    """Resolve only within this workspace; never read another tenant's override."""
    query = select(ModelConfig).where(
        ModelConfig.workspace_id == workspace_id,
        ModelConfig.task == task,
        (ModelConfig.agent_id == agent_id) | ModelConfig.agent_id.is_(None)
        if agent_id is not None
        else ModelConfig.agent_id.is_(None),
    )
    rows = (await db.execute(query)).scalars().all()
    if task == "voice_llm":
        rows = [row for row in rows if normalize_realtime_model(row.model) is not None]
    chosen = next((row for row in rows if row.agent_id == agent_id), None) if agent_id else None
    chosen = chosen or next((row for row in rows if row.agent_id is None), None)
    if chosen is None:
        return Selection(DEFAULTS[task])
    return Selection(chosen.model, chosen.input_usd_per_million, chosen.output_usd_per_million)


def _cost(selection: Selection, input_tokens: int | None, output_tokens: int | None) -> str | None:
    if (
        type(input_tokens) is not int
        or type(output_tokens) is not int
        or input_tokens < 0
        or output_tokens < 0
        or selection.input_usd_per_million is None
        or selection.output_usd_per_million is None
    ):
        return None
    return str(
        (
            Decimal(input_tokens) * selection.input_usd_per_million
            + Decimal(output_tokens) * selection.output_usd_per_million
        )
        / 1_000_000
    )


def log_realtime_usage(selection: Selection, usage: object) -> None:
    """Account for one Realtime response (audio-inclusive tokens as reported by OpenAI)."""
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    structlog.get_logger().info(
        "ai_model_call",
        task="voice_llm",
        model=selection.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost(selection, input_tokens, output_tokens),
    )


def log_model_usage(task: Task, selection: Selection, response: object) -> None:
    """Record one completed OpenAI call, with nullable cost when pricing/usage is unknown."""
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    cost = _cost(selection, input_tokens, output_tokens)
    structlog.get_logger().info(
        "ai_model_call",
        task=task,
        model=getattr(response, "model", None) or selection.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )
