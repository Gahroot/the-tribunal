"""Offline evaluator checks; these fixtures are synthetic, not real-call evidence."""

import json
import uuid
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.embeddings import EmbeddingResult
from app.services.knowledge.retrieval_service import RetrievedPassage, RetrieveOptions
from scripts import eval_knowledge_retrieval as evaluation
from scripts.eval_knowledge_retrieval import Case, load_cases, score_results


def test_document_hit_is_not_an_answer_hit() -> None:
    doc = uuid.uuid4()
    case = Case(uuid.uuid4(), uuid.uuid4(), "Refund?", doc, "within 30 days", "policy")
    wrong_section = RetrievedPassage(doc, "Policies", "Shipping is free", 0.9, 0)
    assert score_results(case, [wrong_section]) == (1.0, 0.0, 1.0)
    right_section = RetrievedPassage(doc, "Policies", "Refunds within\n30 days", 0.8, 1)
    unrelated = RetrievedPassage(uuid.uuid4(), "Other", "within 30 days", 1.0, 0)
    assert score_results(case, [unrelated, right_section]) == (1.0, 1.0, 0.5)
    assert score_results(case, [unrelated]) == (0.0, 0.0, 0.0)


def test_load_cases_requires_reviewed_answer_and_category(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    row = {
        "workspace_id": str(uuid.uuid4()),
        "agent_id": str(uuid.uuid4()),
        "expected_document_id": str(uuid.uuid4()),
        "query": "What is the deposit?",
        "expected_text": "$50 deposit",
        "category": "pricing",
    }
    path.write_text(json.dumps(row))
    assert load_cases(path)[0].expected_text == "$50 deposit"
    row["expected_text"] = " "
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="length"):
        load_cases(path)
    row["expected_text"] = "$50 deposit"
    row["category"] = "unreviewed"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="category"):
        load_cases(path)


@pytest.mark.asyncio
async def test_evaluation_shares_embedding_and_reports_answer_hits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = Case(uuid.uuid4(), uuid.uuid4(), "Refund?", uuid.uuid4(), "30 days", "policy")
    monkeypatch.setattr(evaluation, "load_cases", lambda _path: [case])
    db = AsyncMock()
    db.scalar.return_value = "Refunds within 30 days"
    session = MagicMock()
    session.return_value.__aenter__.return_value = db
    monkeypatch.setattr(evaluation, "AsyncSessionLocal", session)
    embedding = EmbeddingResult(ok=True, embeddings=[[0.1] * 1536])
    embed = AsyncMock(return_value=embedding)
    monkeypatch.setattr(evaluation, "embed_texts", embed)
    modes = []

    async def retrieve(_self: object, _db: object, **kwargs: object) -> list[RetrievedPassage]:
        opts = cast(RetrieveOptions, kwargs["options"])
        modes.append((opts.hybrid, opts.use_mmr))
        assert opts.embedder is not None
        assert await opts.embedder([case.query]) is embedding
        return [RetrievedPassage(case.expected_document_id, "Policies", "30 days", 1.0, 0)]

    monkeypatch.setattr(evaluation.KnowledgeRetrievalService, "retrieve_passages", retrieve)
    await evaluation.evaluate(Path("unused"), 5)
    embed.assert_awaited_once_with([case.query])
    assert modes == [(False, False), (True, True)]
    assert str(db.execute.await_args.args[0]) == "SET TRANSACTION READ ONLY"
    output = capsys.readouterr().out
    assert "answer_hit@5=100.0%" in output
    assert "MRR=1.000" in output
    assert case.query not in output


@pytest.mark.asyncio
async def test_evaluation_rejects_out_of_scope_labels_before_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case(uuid.uuid4(), uuid.uuid4(), "Refund?", uuid.uuid4(), "30 days", "policy")
    monkeypatch.setattr(evaluation, "load_cases", lambda _path: [case])
    db = AsyncMock()
    db.scalar.return_value = None
    session = MagicMock()
    session.return_value.__aenter__.return_value = db
    monkeypatch.setattr(evaluation, "AsyncSessionLocal", session)
    embed = AsyncMock()
    monkeypatch.setattr(evaluation, "embed_texts", embed)
    with pytest.raises(ValueError, match="label at case 1"):
        await evaluation.evaluate(Path("unused"), 5)
    embed.assert_not_awaited()
