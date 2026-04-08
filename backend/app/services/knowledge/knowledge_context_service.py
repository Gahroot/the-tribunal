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

    async def get_context_for_agent(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        token_budget: int | None = None,
    ) -> str:
        """Fetch active KnowledgeDocuments for an agent.

        Orders by priority DESC then created_at ASC.

        Concatenate until token_budget is exhausted.

        Returns formatted string:
        [KNOWLEDGE BASE]
        ## {title}
        {content}

        ## {title2}
        {content2}

        Returns empty string if no documents.
        """
        budget = token_budget if token_budget is not None else self.TOKEN_BUDGET_DEFAULT

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
                logger.debug(
                    "knowledge_context_budget_exceeded",
                    agent_id=str(agent_id),
                    skipped_doc=str(doc.id),
                    tokens_used=tokens_used,
                    budget=budget,
                )
                break

            sections.append(section)
            tokens_used += section_tokens

        if not sections:
            return ""

        logger.info(
            "knowledge_context_assembled",
            agent_id=str(agent_id),
            doc_count=len(sections),
            tokens_used=tokens_used,
            budget=budget,
        )

        return "[KNOWLEDGE BASE]\n" + "\n\n".join(sections)

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
