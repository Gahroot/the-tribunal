#!/usr/bin/env python3
"""Measure hit@k on reviewed, anonymized mid-call questions.

Input JSONL: {"workspace_id": "...", "agent_id": "...", "query": "...",
"expected_document_id": "..."}. Label the correct document by reviewing the
call and its knowledge base; do not copy caller PII into this file. No call text
or retrieved customer content is logged. Run from backend with:

    uv run python scripts/eval_knowledge_retrieval.py --cases /private/path/cases.jsonl

Requires a reachable database and OpenAI embedding credentials. Read-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.knowledge.retrieval_service import KnowledgeRetrievalService, RetrieveOptions


async def evaluate(path: Path, top_k: int) -> None:
    if path.stat().st_size > 1_000_000:
        raise ValueError("Question file exceeds 1 MB")
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not 1 <= len(cases) <= 1000:
        raise ValueError("Expected 1 to 1000 labeled questions")
    service = KnowledgeRetrievalService()
    counts = {"dense": 0, "hybrid": 0}
    async with AsyncSessionLocal() as db:
        for index, case in enumerate(cases, start=1):
            workspace = uuid.UUID(case["workspace_id"])
            agent = uuid.UUID(case["agent_id"])
            expected = uuid.UUID(case["expected_document_id"])
            query = case["query"].strip()
            if not query or len(query) > 1000:
                raise ValueError(f"Invalid query length at case {index}")
            for mode, hybrid in (("dense", False), ("hybrid", True)):
                results = await service.retrieve(
                    db,
                    workspace_id=workspace,
                    agent_id=agent,
                    query=query,
                    options=RetrieveOptions(top_k=top_k, hybrid=hybrid),
                )
                counts[mode] += expected in {result.document_id for result in results}
    for mode, hits in counts.items():
        print(f"{mode} hit@{top_k}: {hits}/{len(cases)} ({hits / len(cases):.1%})")


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
