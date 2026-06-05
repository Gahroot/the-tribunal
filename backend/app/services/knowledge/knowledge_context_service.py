"""Builds CAG context strings from KnowledgeDocuments for prompt injection."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import func

from app.models.knowledge_document import KnowledgeDocument

logger = structlog.get_logger()


class KnowledgeContextService:
    """Builds CAG context strings from KnowledgeDocuments for prompt injection."""

    TOKEN_BUDGET_DEFAULT = 4000  # ~4k tokens default budget per agent
    # Small budget for the always-on "preamble" injected into the prompt. Bulk
    # knowledge now lives behind the on-demand ``search_knowledge`` tool, so the
    # preamble only carries the highest-priority must-know facts (persona, top
    # policies) to keep the prompt lean and avoid static prompt-stuffing.
    PREAMBLE_TOKEN_BUDGET = 700

    async def get_preamble_for_agent(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        token_budget: int | None = None,
    ) -> str:
        """Return a small, high-priority knowledge preamble for prompt injection.

        Rather than greedily concatenating the whole knowledge base up to ~4k
        tokens (the old CAG behavior, now removed), this returns only the
        highest-priority active documents within a tight budget. The bulk of the
        knowledge base is reached on demand via the ``search_knowledge`` tool, so
        this preamble exists purely to seed must-know context (persona, top
        policies) without prompt-stuffing.

        Returns an empty string when there are no documents.
        """
        budget = token_budget if token_budget is not None else self.PREAMBLE_TOKEN_BUDGET

        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.agent_id == agent_id,
                KnowledgeDocument.is_active.is_(True),
            )
            .order_by(
                KnowledgeDocument.priority.desc(),
                KnowledgeDocument.created_at.asc(),
            )
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()

        if not docs:
            return ""

        sections: list[str] = []
        tokens_used = 0
        for doc in docs:
            section = f"## {doc.title}\n{doc.content}"
            section_tokens = self.count_tokens(section)
            if tokens_used + section_tokens > budget:
                break
            sections.append(section)
            tokens_used += section_tokens

        if not sections:
            return ""

        logger.info(
            "knowledge_preamble_assembled",
            agent_id=str(agent_id),
            doc_count=len(sections),
            tokens_used=tokens_used,
            budget=budget,
        )

        return (
            "[KNOWLEDGE BASE \u2014 KEY FACTS]\n"
            "These are the most important reference facts. For anything not "
            "covered here, use the search_knowledge tool to look it up instead "
            "of guessing.\n\n" + "\n\n".join(sections)
        )

    async def has_active_documents(self, db: AsyncSession, agent_id: uuid.UUID) -> bool:
        """Return whether the agent has any active knowledge documents."""
        stmt = select(func.count(KnowledgeDocument.id)).where(
            KnowledgeDocument.agent_id == agent_id,
            KnowledgeDocument.is_active.is_(True),
        )
        result = await db.execute(stmt)
        count: int = result.scalar_one()
        return count > 0

    def count_tokens(self, text: str) -> int:
        """Count tokens using a simple heuristic.

        Uses len(text) // 4 as a reasonable approximation (~4 chars per token)
        to avoid a tiktoken dependency.
        """
        return len(text) // 4

    async def get_total_tokens(self, db: AsyncSession, agent_id: uuid.UUID) -> int:
        """SUM(token_count) for all active docs for an agent. Uses SQL aggregate."""
        stmt = select(func.coalesce(func.sum(KnowledgeDocument.token_count), 0)).where(
            KnowledgeDocument.agent_id == agent_id,
            KnowledgeDocument.is_active.is_(True),
        )
        result = await db.execute(stmt)
        total: int = result.scalar_one()
        return total


knowledge_context_service = KnowledgeContextService()
