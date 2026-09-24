#!/usr/bin/env python3
"""Compare dense and hybrid retrieval on reviewed, anonymized mid-call questions.

Input JSONL: {"workspace_id": "...", "agent_id": "...", "query": "...",
"expected_document_id": "...", "expected_text": "exact answer excerpt",
"category": "pricing"}. Category must be pricing or policy. Label the correct
answer by reviewing the call and its knowledge base; do not copy caller PII.
No queries or retrieved customer content are logged. Run from backend with:

    PYTHONPATH=. uv run python scripts/eval_knowledge_retrieval.py --cases /private/cases.jsonl

Requires a reachable database and OpenAI embedding credentials. Read-only.
Reports document hit@k, answer-passage hit@k and document MRR, grouped by category.
The answer excerpt prevents a hit on an unrelated section of a large document
from counting as successful answer retrieval. Both modes share one query vector.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.embeddings import EmbeddingResult, embed_texts
from app.services.knowledge.retrieval_service import (
    KnowledgeRetrievalService,
    RetrievedPassage,
    RetrieveOptions,
)


@dataclass(frozen=True)
class Case:
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    query: str
    expected_document_id: uuid.UUID
    expected_text: str
    category: str


def load_cases(path: Path) -> list[Case]:
    if path.stat().st_size > 1_000_000:
        raise ValueError("Question file exceeds 1 MB")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not 1 <= len(rows) <= 1000:
        raise ValueError("Expected 1 to 1000 labeled questions")
    cases = []
    for index, row in enumerate(rows, start=1):
        query = row["query"].strip()
        expected_text = row["expected_text"].strip()
        if not query or len(query) > 1000 or not expected_text or len(expected_text) > 1600:
            raise ValueError(f"Invalid query/answer length at case {index}")
        if row["category"] not in {"pricing", "policy"}:
            raise ValueError(f"Invalid category at case {index}")
        cases.append(
            Case(
                uuid.UUID(row["workspace_id"]),
                uuid.UUID(row["agent_id"]),
                query,
                uuid.UUID(row["expected_document_id"]),
                expected_text,
                row["category"],
            )
        )
    return cases


def score_results(case: Case, results: list[RetrievedPassage]) -> tuple[float, float, float]:
    """Document hit, answer-passage hit, reciprocal rank of first correct document."""
    ranks = [
        rank
        for rank, result in enumerate(results, start=1)
        if result.document_id == case.expected_document_id
    ]
    answer_hit = any(
        result.document_id == case.expected_document_id
        and " ".join(case.expected_text.split()) in " ".join(result.content.split())
        for result in results
    )
    return float(bool(ranks)), float(answer_hit), 1 / ranks[0] if ranks else 0.0


async def evaluate(path: Path, top_k: int) -> None:
    cases = load_cases(path)
    service = KnowledgeRetrievalService()
    scores: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        # Validate all labels before spending on embeddings; inactive or foreign
        # documents must never produce misleading zero scores or cross-tenant hits.
        for index, case in enumerate(cases, start=1):
            content = await db.scalar(
                select(KnowledgeDocument.content).where(
                    KnowledgeDocument.id == case.expected_document_id,
                    KnowledgeDocument.workspace_id == case.workspace_id,
                    KnowledgeDocument.agent_id == case.agent_id,
                    KnowledgeDocument.is_active.is_(True),
                )
            )
            if content is None or " ".join(case.expected_text.split()) not in " ".join(
                content.split()
            ):
                raise ValueError(f"Invalid document/answer label at case {index}")

        for index, case in enumerate(cases, start=1):
            embedding = await embed_texts([case.query])
            if not embedding.ok or not embedding.embeddings:
                raise RuntimeError(f"Embedding unavailable at case {index}; comparison aborted")

            async def shared_embedding(
                texts: list[str],
                result: EmbeddingResult = embedding,
            ) -> EmbeddingResult:
                return result

            for mode, hybrid in (("dense", False), ("hybrid_rrf_mmr", True)):
                results = await service.retrieve_passages(
                    db,
                    workspace_id=case.workspace_id,
                    agent_id=case.agent_id,
                    query=case.query,
                    options=RetrieveOptions(
                        top_k=top_k,
                        hybrid=hybrid,
                        use_mmr=hybrid,
                        embedder=shared_embedding,
                    ),
                )
                score = score_results(case, results)
                for group in ("all", case.category):
                    scores.setdefault((mode, group), []).append(score)
    for (mode, group), values in scores.items():
        hits, answers, reciprocal_ranks = map(sum, zip(*values, strict=True))
        count = len(values)
        print(
            f"{mode} {group} n={count}: document_hit@{top_k}={hits / count:.1%} "
            f"answer_hit@{top_k}={answers / count:.1%} MRR={reciprocal_ranks / count:.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10:
        parser.error("top-k must be between 1 and 10")
    asyncio.run(evaluate(args.cases, args.top_k))


if __name__ == "__main__":
    main()
