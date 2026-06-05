"""Shared executor for the on-demand ``search_knowledge`` agent tool.

Both the voice (:class:`~app.services.ai.tool_executor.VoiceToolExecutor`) and
text (:class:`~app.services.ai.text_tool_executor.TextToolExecutor`) agents call
this single entry point so the retrieval contract — query normalization,
``top_k`` clamping, workspace + agent scoping, and the citation-friendly result
shape — stays identical across channels.

This replaces static prompt-stuffing (the old ~4k-token CAG concat): the model
asks for exactly the passages it needs and gets back ranked snippets tagged with
their source document title.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge.retrieval_service import (
    DEFAULT_TOP_K,
    knowledge_retrieval_service,
)

logger = structlog.get_logger()

# Hard ceiling on passages returned per call, independent of what the model asks
# for, to bound prompt growth and latency on the hot path.
MAX_TOP_K = 10


def _clamp_top_k(top_k: int | None) -> int:
    """Clamp a model-supplied ``top_k`` into ``[1, MAX_TOP_K]`` (default 5)."""
    if top_k is None:
        return DEFAULT_TOP_K
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        return DEFAULT_TOP_K
    if value < 1:
        return 1
    if value > MAX_TOP_K:
        return MAX_TOP_K
    return value


async def execute_knowledge_search(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
) -> dict[str, object]:
    """Run hybrid retrieval for ``query`` and shape it for a tool response.

    Always scoped to ``workspace_id`` + ``agent_id`` so one tenant can never read
    another's knowledge base. Returns a JSON-serializable dict with ranked
    ``passages`` (each carrying its source document ``title`` for citation) plus a
    short ``message`` guiding the model to ground its answer in them.
    """
    log = logger.bind(
        service="knowledge_search_tool",
        workspace_id=str(workspace_id),
        agent_id=str(agent_id),
    )

    trimmed = (query or "").strip()
    if not trimmed:
        return {
            "success": False,
            "error": "Provide a non-empty query describing what to look up.",
        }

    resolved_top_k = _clamp_top_k(top_k)

    passages = await knowledge_retrieval_service.retrieve_passages(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
        query=trimmed,
        top_k=resolved_top_k,
    )

    log.info(
        "knowledge_search_executed",
        query=trimmed,
        top_k=resolved_top_k,
        passage_count=len(passages),
    )

    if not passages:
        return {
            "success": True,
            "passages": [],
            "message": (
                "No matching information was found in the knowledge base for that "
                "query. Do NOT make up an answer — tell the caller you don't have "
                "that detail, or try a different, more specific search."
            ),
        }

    formatted = [
        {
            "title": passage.title,
            "content": passage.content,
            "score": round(passage.score, 4),
        }
        for passage in passages
    ]

    return {
        "success": True,
        "passages": formatted,
        "message": (
            "Use ONLY these passages to answer. Cite the document title when "
            "relevant and do not invent details that are not present here."
        ),
    }
