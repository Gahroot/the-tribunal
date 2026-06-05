"""Tests for the knowledge ingestion service.

Covers the three guarantees the task pins down:

* **Dedup** — re-ingesting identical content (matching ``content_hash`` chunks
  already present) is a no-op: no embedding call, no deletes, no inserts.
* **Transactional rollback** — an embedding failure raises and the owning
  transaction boundary rolls back, never committing a half-indexed document.
* **Happy path** — chunks are built with embeddings + offsets and per-chunk
  ``content_hash`` so the next run can dedup.

A lightweight fake ``AsyncSession`` stands in for Postgres: the service's DB
surface (existing-hash query, delete, ``add_all``, ``flush``, commit/rollback) is
small and fully exercised without a live database.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.sql.dml import Delete

from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.embeddings import EmbeddingResult
from app.services.knowledge.chunking import chunk_text
from app.services.knowledge.ingestion_service import (
    IngestionError,
    KnowledgeIngestionService,
    chunk_content_hash,
)


class _FakeScalars:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


class _FakeResult:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._values)


class _FakeSession:
    """Minimal async-session stand-in tracking the service's mutations."""

    def __init__(self, *, existing_hashes: list[str] | None = None) -> None:
        self.existing_hashes = list(existing_hashes or [])
        self.added: list[object] = []
        self.deletes = 0
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
        self._in_tx = True

    async def execute(self, stmt: object) -> _FakeResult:
        if isinstance(stmt, Delete):
            self.deletes += 1
            self.existing_hashes = []
            return _FakeResult([])
        # The only other statement is the existing-hash SELECT.
        return _FakeResult(self.existing_hashes)

    def add_all(self, objs: list[object]) -> None:
        self.added.extend(objs)

    async def flush(self) -> None:
        self.flushes += 1

    def in_transaction(self) -> bool:
        return self._in_tx

    async def commit(self) -> None:
        self.commits += 1
        self._in_tx = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self._in_tx = False


def _document(content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        title="Doc",
        content=content,
        doc_type="general",
        token_count=len(content) // 4,
        priority=0,
        is_active=True,
        metadata_={},
    )


def _hashes_for(content: str, *, target_tokens: int = 400, overlap_tokens: int = 80) -> list[str]:
    """The chunk content hashes the service would produce for ``content``."""
    chunks = chunk_text(content, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
    return [chunk_content_hash(chunk.content) for chunk in chunks]


def _ok_embedder(dim: int = 4):
    async def embed(texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(ok=True, embeddings=[[0.1] * dim for _ in texts])

    return embed


def _failing_embedder():
    async def embed(texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(ok=False, error="boom")

    return embed


def _exploding_embedder():
    async def embed(texts: list[str]) -> EmbeddingResult:  # pragma: no cover - must not run
        raise AssertionError("embedder should not be called on a dedup no-op")

    return embed


class TestDedup:
    @pytest.mark.asyncio
    async def test_identical_content_is_a_noop(self) -> None:
        text = "Some knowledge about pricing and refunds.\n\nMore detail here."
        doc = _document(text)
        # Existing chunks already match what re-chunking this content produces.
        session = _FakeSession(existing_hashes=_hashes_for(text))
        service = KnowledgeIngestionService()

        result = await service.reindex_document(session, doc, embedder=_exploding_embedder())

        assert result.skipped is True
        assert result.chunk_count == len(session.existing_hashes)
        assert session.added == []
        assert session.deletes == 0
        assert session.flushes == 0

    @pytest.mark.asyncio
    async def test_changed_content_reindexes(self) -> None:
        doc = _document("brand new content that was never indexed before")
        # Stored hashes belong to the OLD content, so they will not match.
        session = _FakeSession(existing_hashes=["stale-hash"])
        service = KnowledgeIngestionService()

        result = await service.reindex_document(session, doc, embedder=_ok_embedder())

        assert result.skipped is False
        assert result.chunk_count >= 1
        assert session.deletes == 1  # stale chunks cleared
        assert len(session.added) == result.chunk_count

    @pytest.mark.asyncio
    async def test_force_reindexes_even_when_hashes_match(self) -> None:
        text = "unchanged body of knowledge"
        doc = _document(text)
        session = _FakeSession(existing_hashes=_hashes_for(text))
        service = KnowledgeIngestionService()

        result = await service.reindex_document(session, doc, embedder=_ok_embedder(), force=True)

        assert result.skipped is False
        assert session.deletes == 1
        assert len(session.added) == result.chunk_count


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_builds_chunks_with_embeddings_and_offsets(self) -> None:
        text = "\n\n".join(f"Paragraph {i} with a handful of descriptive words." for i in range(6))
        doc = _document(text)
        session = _FakeSession()
        service = KnowledgeIngestionService(target_tokens=8, overlap_tokens=2)

        result = await service.reindex_document(session, doc, embedder=_ok_embedder())

        assert result.chunk_count == len(session.added)
        assert result.chunk_count >= 1
        assert session.flushes == 1
        for chunk in session.added:
            # Offsets round-trip against the source text and carry an embedding.
            assert chunk.content == text[chunk.char_start : chunk.char_end]  # type: ignore[attr-defined]
            assert chunk.embedding == [0.1] * 4  # type: ignore[attr-defined]
            assert chunk.document_id == doc.id  # type: ignore[attr-defined]
            assert len(chunk.content_hash) == 64  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_empty_content_indexes_no_chunks(self) -> None:
        doc = _document("   \n\n   ")
        session = _FakeSession()
        service = KnowledgeIngestionService()

        result = await service.reindex_document(session, doc, embedder=_ok_embedder())

        assert result.chunk_count == 0
        assert result.skipped is True  # no existing chunks, no new chunks -> nothing to do
        assert session.added == []
        assert session.deletes == 0


class TestTransactionalRollback:
    @pytest.mark.asyncio
    async def test_embedding_failure_raises_and_indexes_nothing(self) -> None:
        doc = _document("content that will fail to embed")
        session = _FakeSession()
        service = KnowledgeIngestionService()

        with pytest.raises(IngestionError, match="boom"):
            await service.reindex_document(session, doc, embedder=_failing_embedder())

        # Nothing indexed: no inserts, no flush.
        assert session.added == []
        assert session.flushes == 0

    @pytest.mark.asyncio
    async def test_ingest_document_rolls_back_transaction_on_failure(self) -> None:
        doc = _document("content that will fail to embed")
        session = _FakeSession()
        service = KnowledgeIngestionService()

        with pytest.raises(IngestionError):
            await service.ingest_document(session, doc, embedder=_failing_embedder())

        assert session.rollbacks == 1
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_ingest_document_commits_on_success(self) -> None:
        doc = _document("content that embeds cleanly into one chunk")
        session = _FakeSession()
        service = KnowledgeIngestionService()

        result = await service.ingest_document(session, doc, embedder=_ok_embedder())

        assert result.skipped is False
        assert session.commits == 1
        assert session.rollbacks == 0
        assert len(session.added) == result.chunk_count

    @pytest.mark.asyncio
    async def test_mismatched_embedding_count_raises(self) -> None:
        async def bad_count_embedder(texts: list[str]) -> EmbeddingResult:
            # Return one fewer vector than requested.
            return EmbeddingResult(ok=True, embeddings=[[0.1] * 4 for _ in texts[:-1]])

        doc = _document("\n\n".join(f"para {i} words words words" for i in range(10)))
        session = _FakeSession()
        service = KnowledgeIngestionService(target_tokens=5, overlap_tokens=1)

        with pytest.raises(IngestionError, match="did not match"):
            await service.reindex_document(session, doc, embedder=bad_count_embedder)
