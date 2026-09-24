"""Tests for the hybrid knowledge retrieval service.

Covers RRF fusion, MMR diversity, active-document and workspace scoping,
keyword fallback, and parent-section expansion. Legacy normalization helpers
retain their own compatibility tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.ai.embeddings import EmbeddingResult
from app.services.knowledge.retrieval_service import (
    Candidate,
    KnowledgeRetrievalService,
    RetrievedChunk,
    RetrieveOptions,
    ScoredCandidate,
    _build_keyword_stmt,
    _build_vector_stmt,
    clamp01,
    compute_mmr,
    fuse_and_filter,
    jaccard,
    min_max_normalize,
    mmr_rerank,
    normalize_weights,
    parent_context,
    reciprocal_rank_fusion,
    tokenize,
)


def _candidate(chunk_id: str, content: str, *, v: float = 0.0, k: float = 0.0) -> Candidate:
    return Candidate(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_OID, chunk_id),
        document_id=uuid.uuid5(uuid.NAMESPACE_OID, f"doc-{chunk_id}"),
        content=content,
        ordinal=0,
        char_start=0,
        char_end=len(content),
        vector_score=v,
        keyword_score=k,
    )


# ── Normalization primitives ────────────────────────────────────────────────
class TestNormalization:
    def test_min_max_scales_to_unit_interval(self) -> None:
        assert min_max_normalize([1.0, 2.0, 3.0]) == [0.0, 0.5, 1.0]

    def test_min_max_zero_span_maps_all_to_one(self) -> None:
        # Mirrors noledge `span === 0 ? 1`.
        assert min_max_normalize([0.4, 0.4, 0.4]) == [1.0, 1.0, 1.0]
        assert min_max_normalize([0.9]) == [1.0]

    def test_min_max_empty(self) -> None:
        assert min_max_normalize([]) == []

    def test_clamp01(self) -> None:
        assert clamp01(-0.5) == 0.0
        assert clamp01(1.5) == 1.0
        assert clamp01(0.3) == 0.3

    def test_weights_renormalize_to_sum_one(self) -> None:
        v, k = normalize_weights(0.7, 0.3)
        assert v == pytest.approx(0.7)
        assert k == pytest.approx(0.3)
        v2, k2 = normalize_weights(7, 3)
        assert v2 == pytest.approx(0.7)
        assert k2 == pytest.approx(0.3)

    def test_weights_negative_clamped_and_zero_falls_back_to_vector(self) -> None:
        v, k = normalize_weights(-1, 4)
        assert (v, k) == (0.0, 1.0)
        assert normalize_weights(0, 0) == (1.0, 0.0)


# ── Fusion ──────────────────────────────────────────────────────────────────
class TestFusion:
    def test_weighted_fusion_default_weights(self) -> None:
        candidates = [
            _candidate("a", "alpha", v=1.0, k=0.0),
            _candidate("b", "bravo", v=0.0, k=1.0),
        ]
        scored = fuse_and_filter(candidates, 0.7, 0.3, min_score=0.0)
        by_content = {sc.candidate.content: sc.score for sc in scored}
        # Pure-vector chunk scores 0.7, pure-keyword chunk scores 0.3.
        assert by_content["alpha"] == pytest.approx(0.7)
        assert by_content["bravo"] == pytest.approx(0.3)

    def test_results_sorted_by_score_descending(self) -> None:
        candidates = [
            _candidate("low", "low", v=0.1, k=0.1),
            _candidate("high", "high", v=0.9, k=0.9),
            _candidate("mid", "mid", v=0.5, k=0.5),
        ]
        scored = fuse_and_filter(candidates, 0.7, 0.3, min_score=0.0)
        ordered = [sc.candidate.content for sc in scored]
        assert ordered == ["high", "mid", "low"]

    def test_min_score_floor_drops_weak_candidates(self) -> None:
        candidates = [
            _candidate("strong", "strong", v=0.8, k=0.8),
            _candidate("weak", "weak", v=0.1, k=0.1),
        ]
        scored = fuse_and_filter(candidates, 0.7, 0.3, min_score=0.3)
        contents = [sc.candidate.content for sc in scored]
        assert contents == ["strong"]  # weak (score 0.1) filtered out

    def test_fusion_combines_both_arms(self) -> None:
        # A chunk present in both arms should beat one present in a single arm.
        both = _candidate("both", "both arms", v=0.6, k=0.6)
        vector_only = _candidate("vec", "vector only", v=0.9, k=0.0)
        scored = fuse_and_filter([both, vector_only], 0.7, 0.3, min_score=0.0)
        scores = {sc.candidate.content: sc.score for sc in scored}
        assert scores["both arms"] == pytest.approx(0.6)
        assert scores["vector only"] == pytest.approx(0.63)


# ── MMR diversity ───────────────────────────────────────────────────────────
class TestMmr:
    def test_tokenize_lowercases_alnum_runs(self) -> None:
        assert tokenize("Hello, World-123!") == {"hello", "world", "123"}

    def test_jaccard_bounds(self) -> None:
        assert jaccard(set(), set()) == 0.0
        assert jaccard({"a"}, {"a"}) == 1.0
        assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_compute_mmr_objective(self) -> None:
        # lambda*relevance - (1-lambda)*maxSim
        assert compute_mmr(1.0, 0.0, 0.7) == pytest.approx(0.7)
        # 0.7*1 - 0.3*1 = 0.4
        assert compute_mmr(1.0, 1.0, 0.7) == pytest.approx(0.4)
        # A fully-redundant candidate (sim 1) ties zero only at lambda 0.5.
        assert compute_mmr(1.0, 1.0, 0.5) == pytest.approx(0.0)

    def test_mmr_demotes_near_duplicate(self) -> None:
        # Two near-identical top chunks + one diverse lower chunk. MMR should
        # pick the diverse chunk second instead of the duplicate.
        items = [
            ScoredCandidate(_candidate("a", "the quick brown fox jumps"), score=0.95),
            ScoredCandidate(_candidate("b", "the quick brown fox jumps over"), score=0.90),
            ScoredCandidate(_candidate("c", "unrelated pricing refund policy"), score=0.80),
        ]
        out = mmr_rerank(items, lambda_=0.7, limit=2)
        contents = [sc.candidate.content for sc in out]
        assert contents[0] == "the quick brown fox jumps"  # highest relevance first
        assert contents[1] == "unrelated pricing refund policy"  # diversity wins 2nd

    def test_mmr_pure_relevance_when_lambda_one(self) -> None:
        items = [
            ScoredCandidate(_candidate("a", "alpha alpha alpha"), score=0.9),
            ScoredCandidate(_candidate("b", "alpha alpha alpha"), score=0.8),
            ScoredCandidate(_candidate("c", "beta gamma delta"), score=0.7),
        ]
        out = mmr_rerank(items, lambda_=1.0, limit=3)
        assert [sc.score for sc in out] == [0.9, 0.8, 0.7]

    def test_mmr_respects_limit_and_empty(self) -> None:
        items = [ScoredCandidate(_candidate("a", "x"), score=0.5)]
        assert mmr_rerank(items, limit=0) == []
        assert mmr_rerank([], limit=5) == []
        assert len(mmr_rerank(items, limit=10)) == 1


def test_rrf_preserves_exact_keyword_hit_even_at_last_rank() -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]
    candidates = {key: _candidate(str(key), "policy") for key in ids}
    candidates = {c.chunk_id: c for c in candidates.values()}
    rows = [type("Row", (), {"id": key})() for key in candidates]
    ranked = reciprocal_rank_fusion(
        candidates, [], rows, min_score=0.9, vector_weight=0, keyword_weight=1
    )
    assert [item.candidate.chunk_id for item in ranked] == list(candidates)


def test_parent_context_keeps_policy_with_heading_not_neighbor_section() -> None:
    document = (
        "# Pricing\nBasic $20.\n# Refund policy\nReturns within 30 days.\n# Shipping\nShips Monday."
    )
    start = document.index("Returns")
    chunk = RetrievedChunk(
        uuid.uuid4(), uuid.uuid4(), "Returns within 30 days.", 1, start, start + 23, 0.1, 0.9
    )
    assert parent_context(document, chunk) == "# Refund policy\nReturns within 30 days."
    assert (
        parent_context(
            document, RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "fallback", 1, -1, 0, 0.1, 0.9)
        )
        == "fallback"
    )
    # A document edit before re-indexing must never expand an old hit to new text.
    stale = RetrievedChunk(
        uuid.uuid4(), uuid.uuid4(), "Original policy", 1, start, start + 15, 0.1, 0.9
    )
    assert parent_context(document, stale) == "Original policy"


# ── Workspace + agent scoping (compiled SQL) ────────────────────────────────
class TestScoping:
    def _sql(self, stmt: object) -> str:
        from sqlalchemy.dialects import postgresql

        return str(
            stmt.compile(  # type: ignore[attr-defined]
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": False},
            )
        )

    def test_vector_stmt_scopes_workspace_and_agent(self) -> None:
        ws = uuid.uuid4()
        agent = uuid.uuid4()
        stmt = _build_vector_stmt(ws, agent, [0.0] * 1536, limit=10)
        sql = self._sql(stmt).lower()
        assert "knowledge_chunks.workspace_id =" in sql
        assert "knowledge_chunks.agent_id =" in sql
        assert "join knowledge_documents" in sql
        assert "knowledge_documents.is_active is true" in sql
        assert "knowledge_documents.workspace_id =" in sql
        assert "knowledge_documents.agent_id =" in sql
        # Cosine KNN ordering + over-fetch limit present.
        assert "order by" in sql and "limit" in sql

    def test_keyword_stmt_scopes_workspace_and_agent(self) -> None:
        ws = uuid.uuid4()
        agent = uuid.uuid4()
        stmt = _build_keyword_stmt(ws, agent, "pricing", limit=10)
        sql = self._sql(stmt).lower()
        assert "knowledge_chunks.workspace_id =" in sql
        assert "knowledge_chunks.agent_id =" in sql
        assert "join knowledge_documents" in sql
        assert "knowledge_documents.is_active is true" in sql
        assert "knowledge_documents.workspace_id =" in sql
        assert "knowledge_documents.agent_id =" in sql
        # Keyword arm uses tsvector match + ts_rank.
        assert "ts_rank" in sql
        assert "@@" in sql

    def test_scoping_binds_actual_ids(self) -> None:
        ws = uuid.uuid4()
        agent = uuid.uuid4()
        stmt = _build_vector_stmt(ws, agent, [0.0] * 1536, limit=5)
        params = stmt.compile().params
        bound = list(params.values())
        assert ws in bound
        assert agent in bound


# ── retrieve() short-circuits (no DB access) ────────────────────────────────
class TestRetrieveShortCircuits:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_without_db(self) -> None:
        db = AsyncMock()
        embedder = AsyncMock()
        out = await KnowledgeRetrievalService().retrieve(
            db,
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            query="   ",
            options=RetrieveOptions(embedder=embedder),
        )
        assert out == []
        embedder.assert_not_awaited()
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embed_failure_falls_back_to_keyword_search(self) -> None:
        chunk_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        row = type(
            "Row",
            (),
            {
                "id": chunk_id,
                "document_id": doc_id,
                "content": "Refund policy: 30 days",
                "ordinal": 0,
                "char_start": 0,
                "char_end": 22,
                "rank": 0.1,
            },
        )()
        db = AsyncMock()
        db.execute.return_value.all = lambda: [row]

        async def failing_embedder(_texts: list[str]) -> EmbeddingResult:
            return EmbeddingResult(ok=False, error="boom")

        out = await KnowledgeRetrievalService().retrieve(
            db,
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            query="pricing",
            options=RetrieveOptions(embedder=failing_embedder),
        )
        assert [chunk.content for chunk in out] == ["Refund policy: 30 days"]
        assert db.execute.await_count == 1


def test_keyword_query_matches_any_term_without_interpreting_operators() -> None:
    stmt = _build_keyword_stmt(
        uuid.uuid4(), uuid.uuid4(), 'Can I get a refund? !cancel "OR" policy:*', 15
    )
    params = stmt.compile().params
    assert "can | i | get | a | refund | cancel | or | policy" in params.values()
    assert "to_tsquery" in str(stmt)


@pytest.mark.asyncio
async def test_reranker_can_promote_hit_outside_final_top_k() -> None:
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content=f"policy {index}",
            ordinal=index,
            char_start=0,
            char_end=8,
            distance=0.1 + index / 10,
        )
        for index in range(3)
    ]
    db = AsyncMock()
    db.execute.return_value.all = lambda: rows
    embedder = AsyncMock(return_value=EmbeddingResult(ok=True, embeddings=[[0.1] * 1536]))
    seen = []

    async def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        assert query == "policy"
        seen.extend(chunks)
        return list(reversed(chunks))

    results = await KnowledgeRetrievalService().retrieve(
        db,
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        query="policy",
        options=RetrieveOptions(
            top_k=1,
            hybrid=False,
            use_mmr=False,
            embedder=embedder,
            reranker=rerank,
        ),
    )
    assert len(seen) == 3
    assert [chunk.chunk_id for chunk in results] == [rows[2].id]


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1, 51])
async def test_retrieval_rejects_unbounded_candidate_requests(top_k: int) -> None:
    db = AsyncMock()
    embedder = AsyncMock()
    with pytest.raises(ValueError, match="top_k"):
        await KnowledgeRetrievalService().retrieve(
            db,
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            query="pricing",
            options=RetrieveOptions(top_k=top_k, embedder=embedder),
        )
    db.execute.assert_not_awaited()
    embedder.assert_not_awaited()


# ── retrieve_passages() title enrichment ─────────────────────────────
class TestRetrievePassages:
    @pytest.mark.asyncio
    async def test_empty_retrieval_skips_title_query(self) -> None:
        service = KnowledgeRetrievalService()
        service.retrieve = AsyncMock(return_value=[])  # type: ignore[method-assign]
        db = AsyncMock()

        out = await service.retrieve_passages(
            db,
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            query="pricing",
        )
        assert out == []
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enriches_chunks_with_document_titles(self) -> None:
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()
        chunks = [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=doc_a,
                content="plans start at $49",
                ordinal=0,
                char_start=0,
                char_end=18,
                distance=0.1,
                score=0.9,
            ),
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=doc_b,
                content="unknown doc chunk",
                ordinal=1,
                char_start=0,
                char_end=17,
                distance=0.2,
                score=0.6,
            ),
        ]
        service = KnowledgeRetrievalService()
        service.retrieve = AsyncMock(return_value=chunks)  # type: ignore[method-assign]

        # Only doc_a is active/visible; doc_b must be discarded, not surfaced.
        title_row = type(
            "Row", (), {"id": doc_a, "title": "Pricing", "content": "plans start at $49"}
        )()
        title_result = type("Res", (), {"all": lambda self: [title_row]})()
        db = AsyncMock()
        db.execute.return_value = title_result

        out = await service.retrieve_passages(
            db,
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            query="cost",
            top_k=3,
        )
        assert [(p.title, p.content, p.score) for p in out] == [
            ("Pricing", "plans start at $49", 0.9),
        ]
        from sqlalchemy.dialects import postgresql

        sql = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect())).lower()
        assert "knowledge_documents.is_active is true" in sql
        # top_k override is threaded into the underlying retrieve() options.
        assert service.retrieve.await_args.kwargs["options"].top_k == 3
