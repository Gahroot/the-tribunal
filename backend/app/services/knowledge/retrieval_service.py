"""Workspace/agent-scoped pgvector + Postgres FTS knowledge retrieval.

Both arms over-fetch, RRF fuses their ranks, and MMR diversifies the shortlist.
Hits are expanded to bounded parent sections using offsets in the source document.
Keyword search remains available when the embedding provider fails.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

import structlog
from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.embeddings import Embedder, embed_texts

logger = structlog.get_logger()

# ── Defaults (mirror noledge retrieve.ts) ───────────────────────────────────
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.3
DEFAULT_VECTOR_WEIGHT = 0.5
DEFAULT_KEYWORD_WEIGHT = 0.5
DEFAULT_MMR_LAMBDA = 0.7
# Postgres text-search config used by the generated tsvector column + queries.
TS_CONFIG = "english"

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


# ── Reranker seam (port of rerank.ts) ───────────────────────────────────────
# A reranker reorders (and may trim) retrieved chunks for a query, e.g. with a
# cross-encoder or hosted relevance API. It runs after fusion + MMR. Defaults to
# the identity no-op so no network dependency is added.
Reranker = Callable[[str, list["RetrievedChunk"]], Awaitable[list["RetrievedChunk"]]]


async def identity_reranker(_query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Default reranker: return chunks untouched."""
    return chunks


@dataclass(slots=True)
class Candidate:
    """A chunk surfaced by one or both arms, with normalized per-arm scores."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    ordinal: int
    char_start: int
    char_end: int
    # Best cosine distance from the vector arm (0 = identical). ``inf`` when the
    # chunk surfaced only via the keyword arm.
    distance: float = float("inf")
    # Per-arm scores AFTER min-max normalization, both in ``[0, 1]``.
    vector_score: float = 0.0
    keyword_score: float = 0.0


@dataclass(slots=True)
class RetrievedChunk:
    """A fused, ranked retrieval result."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    ordinal: int
    char_start: int
    char_end: int
    distance: float
    # RRF relevance score (higher = better).
    score: float


@dataclass(slots=True)
class RetrievedPassage:
    """A ranked retrieval result enriched with its source document title.

    This is the citation-friendly shape returned to the on-demand
    ``search_knowledge`` tool: the model gets the passage text plus the human
    title of the document it came from so it can attribute facts out loud.
    """

    document_id: uuid.UUID
    title: str
    content: str
    score: float
    ordinal: int


@dataclass(slots=True)
class ScoredCandidate:
    """A candidate paired with its fused score (intermediate fusion output)."""

    candidate: Candidate
    score: float


@dataclass(slots=True)
class RetrieveOptions:
    """Knobs mirroring noledge ``RetrieveOptions`` (subset that applies here)."""

    top_k: int = DEFAULT_TOP_K
    min_score: float = DEFAULT_MIN_SCORE
    vector_weight: float = DEFAULT_VECTOR_WEIGHT
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT
    hybrid: bool = True
    use_mmr: bool = True
    mmr_lambda: float = DEFAULT_MMR_LAMBDA
    embedder: Embedder | None = None
    reranker: Reranker | None = None
    # Back-compat: max cosine distance for the vector arm. When set, overrides
    # ``min_score`` with ``1 - max_distance`` (matches noledge ``maxDistance``).
    max_distance: float | None = None


# ── Pure helpers ────────────────────────────────────────────────────────────
def clamp01(value: float) -> float:
    """Clamp ``value`` into ``[0, 1]``."""
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def candidate_count(top_k: int) -> int:
    """Per-arm over-fetch so filtering/MMR never under-fills ``top_k``."""
    return max(top_k * 3, top_k + 8)


def min_max_normalize(values: list[float]) -> list[float]:
    """Min-max scale ``values`` into ``[0, 1]``.

    A zero span (all equal, or a single element) maps every entry to ``1.0``,
    matching noledge's ``span === 0 ? 1`` keyword-arm behavior.
    """
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span == 0:
        return [1.0 for _ in values]
    return [(value - lo) / span for value in values]


def normalize_weights(vector_weight: float, keyword_weight: float) -> tuple[float, float]:
    """Clamp negatives to 0 and renormalize the two weights to sum to 1.

    If both are zero, fall back to a pure-vector ``(1, 0)`` split (mirrors the
    reference clamp logic: ``weightSum === 0 ? 1 : ...``).
    """
    v = max(0.0, vector_weight)
    k = max(0.0, keyword_weight)
    total = v + k
    if total == 0:
        return 1.0, 0.0
    return v / total, k / total


def tokenize(text: str) -> set[str]:
    """Lowercase word/number tokens of ``text`` as a set (for Jaccard)."""
    return set(_TOKEN_PATTERN.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity ``|a ∩ b| / |a ∪ b|`` in ``[0, 1]``; empty/empty → 0."""
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a) + len(b) - intersection
    return 0.0 if union == 0 else intersection / union


def compute_mmr(relevance: float, max_sim: float, lambda_: float) -> float:
    """MMR objective for one candidate: ``λ·relevance − (1−λ)·maxSim``."""
    return lambda_ * relevance - (1 - lambda_) * max_sim


def mmr_rerank(
    items: list[ScoredCandidate],
    lambda_: float = DEFAULT_MMR_LAMBDA,
    limit: int | None = None,
) -> list[ScoredCandidate]:
    """Greedy MMR rerank (token-Jaccard similarity). Pure and deterministic.

    Input order is the tie-breaker, so passing items pre-sorted by score keeps
    results stable. Port of noledge ``mmrRerank``.
    """
    cap = len(items) if limit is None else limit
    if not items or cap <= 0:
        return []

    tokens = [tokenize(item.candidate.content) for item in items]
    remaining = list(range(len(items)))
    selected: list[int] = []

    while len(selected) < cap and remaining:
        best_pos = 0
        best_value = float("-inf")
        for pos, index in enumerate(remaining):
            max_sim = 0.0
            for chosen in selected:
                sim = jaccard(tokens[index], tokens[chosen])
                max_sim = max(max_sim, sim)
            value = compute_mmr(items[index].score, max_sim, lambda_)
            if value > best_value:
                best_value = value
                best_pos = pos
        selected.append(remaining.pop(best_pos))

    return [items[index] for index in selected]


def fuse_and_filter(
    candidates: list[Candidate],
    vector_weight: float,
    keyword_weight: float,
    min_score: float,
) -> list[ScoredCandidate]:
    """Weighted-fuse the two normalized arms, drop sub-floor, sort by score.

    Weights are renormalized to sum to 1 first. Mirrors the fusion block of
    noledge ``retrieveChunks``.
    """
    v_weight, k_weight = normalize_weights(vector_weight, keyword_weight)
    scored = [
        ScoredCandidate(
            candidate=candidate,
            score=v_weight * candidate.vector_score + k_weight * candidate.keyword_score,
        )
        for candidate in candidates
    ]
    survivors = [entry for entry in scored if entry.score >= min_score]
    survivors.sort(key=lambda entry: entry.score, reverse=True)
    return survivors


SearchRow = Row[tuple[uuid.UUID, uuid.UUID, str, int, int, int, float]]


def reciprocal_rank_fusion(
    candidates: dict[uuid.UUID, Candidate],
    vector_rows: Sequence[SearchRow],
    keyword_rows: Sequence[SearchRow],
    *,
    min_score: float,
    vector_weight: float,
    keyword_weight: float,
) -> list[ScoredCandidate]:
    """Fuse ranked shortlists, not incomparable raw distances and ts_rank values.

    A single-arm hit retains its full rank contribution. The score floor applies
    to cosine similarity only for dense-only hits; lexical matches must remain
    eligible even when dense retrieval misses a proper noun or exact price.
    """
    weights = normalize_weights(vector_weight, keyword_weight)
    if not vector_rows:
        weights = (0.0, 1.0)
    if not keyword_rows:
        weights = (1.0, 0.0)
    scores: dict[uuid.UUID, float] = {}
    for rows, weight in zip((vector_rows, keyword_rows), weights, strict=True):
        for rank, row in enumerate(rows, start=1):
            scores[row.id] = scores.get(row.id, 0.0) + weight / (60 + rank)
    lexical_ids = {row.id for row in keyword_rows}
    results = [
        ScoredCandidate(candidate, score * 61)
        for chunk_id, score in scores.items()
        if (candidate := candidates[chunk_id]).chunk_id in lexical_ids
        or 1.0 - candidate.distance >= min_score
    ]
    return sorted(results, key=lambda item: (-item.score, str(item.candidate.chunk_id)))


_HEADING = re.compile(r"(?m)^#{1,6}\s+[^\n]+$")
MAX_PARENT_CHARS = 1600


def parent_context(document: str, chunk: RetrievedChunk) -> str:
    """Expand a child hit to its bounded parent section without crossing headings.

    Old chunks work immediately: offsets already point into the original document.
    Invalid offsets fall back to stored child content instead of unrelated text.
    """
    if not (0 <= chunk.char_start < chunk.char_end <= len(document)):
        return chunk.content
    if chunk.char_end - chunk.char_start >= MAX_PARENT_CHARS:
        return chunk.content
    headings = list(_HEADING.finditer(document))
    before = [heading for heading in headings if heading.start() <= chunk.char_start]
    section_start = before[-1].start() if before else 0
    section_end = next(
        (heading.start() for heading in headings if heading.start() >= chunk.char_end),
        len(document),
    )
    if section_end - section_start <= MAX_PARENT_CHARS:
        return document[section_start:section_end].strip()
    # Keep the hit, a little surrounding context, and the section heading.
    start = max(section_start, chunk.char_start - 200)
    end = min(section_end, max(chunk.char_end, start + MAX_PARENT_CHARS))
    if end - start > MAX_PARENT_CHARS:
        start = max(section_start, end - MAX_PARENT_CHARS)
    body = document[start:end].strip()
    if before and start > section_start:
        heading = before[-1].group().strip()
        if not body.startswith(heading):
            body = f"{heading}\n{body}"
    return body


# ── DB query builders (workspace + agent scoped) ────────────────────────────
def _build_vector_stmt(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    query_vector: list[float],
    limit: int,
) -> Select[tuple[uuid.UUID, uuid.UUID, str, int, int, int, float]]:
    """KNN over-fetch ordered by cosine distance, scoped to workspace + agent."""
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
    return (
        select(
            KnowledgeChunk.id,
            KnowledgeChunk.document_id,
            KnowledgeChunk.content,
            KnowledgeChunk.ordinal,
            KnowledgeChunk.char_start,
            KnowledgeChunk.char_end,
            distance,
        )
        .where(
            KnowledgeChunk.workspace_id == workspace_id,
            KnowledgeChunk.agent_id == agent_id,
        )
        .order_by(distance.asc())
        .limit(limit)
    )


def _build_keyword_stmt(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    query: str,
    limit: int,
) -> Select[tuple[uuid.UUID, uuid.UUID, str, int, int, int, float]]:
    """Full-text over-fetch ranked by ts_rank, scoped to workspace + agent."""
    ts_query = func.websearch_to_tsquery(TS_CONFIG, query)
    rank = func.ts_rank(KnowledgeChunk.search_vector, ts_query).label("rank")
    return (
        select(
            KnowledgeChunk.id,
            KnowledgeChunk.document_id,
            KnowledgeChunk.content,
            KnowledgeChunk.ordinal,
            KnowledgeChunk.char_start,
            KnowledgeChunk.char_end,
            rank,
        )
        .where(
            KnowledgeChunk.workspace_id == workspace_id,
            KnowledgeChunk.agent_id == agent_id,
            KnowledgeChunk.search_vector.op("@@")(ts_query),
        )
        .order_by(rank.desc())
        .limit(limit)
    )


class KnowledgeRetrievalService:
    """Hybrid vector + keyword retrieval over ``knowledge_chunks``."""

    async def retrieve(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        query: str,
        options: RetrieveOptions | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k most relevant chunks for ``query``.

        Over-fetch per arm → RRF → MMR diversify → slice to ``top_k``.
        ``min_score`` gates dense-only cosine hits, not exact lexical hits.
        """
        opts = options or RetrieveOptions()
        embedder = opts.embedder or embed_texts
        reranker = opts.reranker or identity_reranker

        min_score = (
            clamp01(1 - opts.max_distance) if opts.max_distance is not None else opts.min_score
        )

        trimmed = query.strip()
        if not trimmed:
            return []

        embedded = await embedder([trimmed])
        query_vector = embedded.embeddings[0] if embedded.ok and embedded.embeddings else None
        if query_vector is None:
            logger.warning(
                "knowledge_retrieval_embed_failed",
                workspace_id=str(workspace_id),
                agent_id=str(agent_id),
                error=embedded.error,
            )
            if not opts.hybrid:
                return []

        candidate_k = candidate_count(opts.top_k)
        candidates: dict[uuid.UUID, Candidate] = {}

        # ── Vector arm ──────────────────────────────────────────────────────
        vector_rows = (
            (
                await db.execute(
                    _build_vector_stmt(workspace_id, agent_id, query_vector, candidate_k)
                )
            ).all()
            if query_vector is not None
            else []
        )
        for row in vector_rows:
            candidates[row.id] = Candidate(
                chunk_id=row.id,
                document_id=row.document_id,
                content=row.content,
                ordinal=row.ordinal,
                char_start=row.char_start,
                char_end=row.char_end,
                distance=float(row.distance),
                vector_score=0.0,
                keyword_score=0.0,
            )

        # ── Keyword arm ─────────────────────────────────────────────────────
        keyword_rows: Sequence[SearchRow] = []
        if opts.hybrid:
            keyword_rows = (
                await db.execute(_build_keyword_stmt(workspace_id, agent_id, trimmed, candidate_k))
            ).all()
            for row in keyword_rows:
                existing = candidates.get(row.id)
                if existing is not None:
                    existing.keyword_score = 1.0
                    continue
                candidates[row.id] = Candidate(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    content=row.content,
                    ordinal=row.ordinal,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    distance=float("inf"),
                    vector_score=0.0,
                    keyword_score=1.0,
                )

        # ── Fuse → filter → MMR → slice ─────────────────────────────────────
        # Rank fusion is stable across cosine and ts_rank score scales. In
        # particular, a keyword-only pricing hit is not penalized just because
        # it was absent from the dense arm's shortlist.
        scored = reciprocal_rank_fusion(
            candidates,
            vector_rows,
            keyword_rows if opts.hybrid else [],
            min_score=min_score,
            vector_weight=opts.vector_weight if query_vector is not None else 0.0,
            keyword_weight=opts.keyword_weight if opts.hybrid else 0.0,
        )
        selected = (
            mmr_rerank(scored, lambda_=opts.mmr_lambda, limit=opts.top_k)
            if opts.use_mmr
            else scored[: opts.top_k]
        )

        chunks = [
            RetrievedChunk(
                chunk_id=entry.candidate.chunk_id,
                document_id=entry.candidate.document_id,
                content=entry.candidate.content,
                ordinal=entry.candidate.ordinal,
                char_start=entry.candidate.char_start,
                char_end=entry.candidate.char_end,
                distance=entry.candidate.distance,
                score=entry.score,
            )
            for entry in selected
        ]
        return await reranker(trimmed, chunks)

    async def retrieve_passages(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        options: RetrieveOptions | None = None,
    ) -> list[RetrievedPassage]:
        """Retrieve the top-k chunks and enrich them with document titles.

        Thin wrapper over :meth:`retrieve` for the on-demand ``search_knowledge``
        tool: runs the hybrid pipeline (always scoped to ``workspace_id`` +
        ``agent_id``), then resolves each surviving chunk's parent document title
        in a single query so the model can cite sources. Order is preserved.
        """
        opts = options or RetrieveOptions()
        if top_k is not None:
            opts = replace(opts, top_k=top_k)

        chunks = await self.retrieve(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            query=query,
            options=opts,
        )
        if not chunks:
            return []

        document_ids = {chunk.document_id for chunk in chunks}
        title_rows = (
            await db.execute(
                select(
                    KnowledgeDocument.id, KnowledgeDocument.title, KnowledgeDocument.content
                ).where(
                    KnowledgeDocument.id.in_(document_ids),
                    KnowledgeDocument.workspace_id == workspace_id,
                    KnowledgeDocument.agent_id == agent_id,
                )
            )
        ).all()
        documents = {row.id: row for row in title_rows}

        return [
            RetrievedPassage(
                document_id=chunk.document_id,
                title=documents[chunk.document_id].title
                if chunk.document_id in documents
                else "Untitled",
                content=parent_context(documents[chunk.document_id].content, chunk)
                if chunk.document_id in documents
                else chunk.content,
                score=chunk.score,
                ordinal=chunk.ordinal,
            )
            for chunk in chunks
        ]


knowledge_retrieval_service = KnowledgeRetrievalService()
