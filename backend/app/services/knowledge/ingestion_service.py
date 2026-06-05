"""Knowledge document ingestion — chunk, embed, and store in one transaction.

Python port of noledge's ``src/lib/ingest/ingest.ts``. Given a persisted
:class:`KnowledgeDocument`, this service:

1. **Chunks** the document text with the token-aware recursive splitter
   (:mod:`app.services.knowledge.chunking`), recording ``char_start`` /
   ``char_end`` offsets per chunk.
2. **Batch-embeds** the chunks via :func:`app.services.ai.embeddings.embed_texts`
   (OpenAI ``text-embedding-3-small``, 1536 dims).
3. **Stores** the chunks + embeddings, replacing any prior chunks for the
   document, inside the *caller's* transaction so the document row and its
   chunks commit (or roll back) atomically.

Re-ingest is idempotent: each chunk stores a SHA-256 hash of its content in the
purpose-built ``knowledge_chunks.content_hash`` column. On re-ingest the freshly
computed chunk hashes are compared against the document's stored chunk hashes; if
they are identical the run is a **no-op** — no embedding spend, no writes. Any
failure (embedding error, DB error) raises and leaves the caller's transaction to
roll back, so a document never ends up half-indexed.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import transaction_boundary
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.embeddings import Embedder, embed_texts
from app.services.knowledge.chunking import (
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_TARGET_TOKENS,
    TextChunk,
    chunk_text,
)

logger = structlog.get_logger()

# Per-request batch size for the embeddings API. OpenAI accepts large input
# arrays; 128 keeps any single request well under payload/timeout limits while
# minimizing round-trips for big documents.
EMBED_BATCH_SIZE = 128


class IngestionError(Exception):
    """Raised when a document cannot be chunked + embedded.

    The caller's transaction boundary is responsible for rolling back; this
    exception simply signals that nothing was successfully indexed.
    """


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of an ingest run."""

    document_id: uuid.UUID
    chunk_count: int
    # ``True`` when dedup short-circuited (identical content already indexed).
    skipped: bool


def chunk_content_hash(text: str) -> str:
    """SHA-256 (hex) of a chunk's content, stored in ``knowledge_chunks.content_hash``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KnowledgeIngestionService:
    """Chunk + embed + persist knowledge documents."""

    def __init__(
        self,
        *,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ) -> None:
        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens

    async def reindex_document(
        self,
        db: AsyncSession,
        document: KnowledgeDocument,
        *,
        embedder: Embedder | None = None,
        force: bool = False,
    ) -> IngestionResult:
        """Re-chunk + re-embed ``document`` within the caller's transaction.

        Does **not** commit — the caller owns the transaction boundary so the
        document mutation and its chunks are one atomic unit. Raises
        :class:`IngestionError` on embedding failure (leaving the caller to roll
        back).

        Args:
            db: Active session; mutations are flushed but not committed here.
            document: A persisted document with ``id`` / ``workspace_id`` /
                ``agent_id`` / ``content`` populated.
            embedder: Embedding callable; defaults to the OpenAI embedder.
            force: Re-embed even when the chunk content hashes are unchanged.
        """
        embed = embedder or embed_texts

        chunks = chunk_text(
            document.content,
            target_tokens=self._target_tokens,
            overlap_tokens=self._overlap_tokens,
        )
        new_hashes = [chunk_content_hash(chunk.content) for chunk in chunks]

        # Dedup against the purpose-built ``content_hash`` column: if the new
        # chunk hashes match what is already stored (same chunks, same order),
        # the document is already current and we skip the embedding spend.
        existing_hashes = await self._existing_chunk_hashes(db, document.id)
        if not force and existing_hashes == new_hashes:
            logger.info(
                "knowledge_ingest_skipped",
                document_id=str(document.id),
                reason="content_unchanged",
                chunk_count=len(existing_hashes),
            )
            return IngestionResult(
                document_id=document.id,
                chunk_count=len(existing_hashes),
                skipped=True,
            )

        # Replace any prior chunks so re-ingest never leaves stale slices behind.
        if existing_hashes:
            await db.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
            )

        if chunks:
            embeddings = await self._embed_chunks(embed, [chunk.content for chunk in chunks])
            db.add_all(
                [
                    self._build_chunk(document, chunk, vector, content_hash)
                    for chunk, vector, content_hash in zip(
                        chunks, embeddings, new_hashes, strict=True
                    )
                ]
            )
        await db.flush()

        logger.info(
            "knowledge_ingest_completed",
            document_id=str(document.id),
            chunk_count=len(chunks),
        )
        return IngestionResult(
            document_id=document.id,
            chunk_count=len(chunks),
            skipped=False,
        )

    async def ingest_document(
        self,
        db: AsyncSession,
        document: KnowledgeDocument,
        *,
        embedder: Embedder | None = None,
        force: bool = False,
    ) -> IngestionResult:
        """Reindex ``document`` and own the commit/rollback (standalone path).

        Use this from scripts / backfills where the caller is not already inside
        a unit-of-work boundary. The API request path uses
        :meth:`reindex_document` so it shares the request's single transaction.
        """
        async with transaction_boundary(db):
            return await self.reindex_document(db, document, embedder=embedder, force=force)

    # ── internals ────────────────────────────────────────────────────────────
    async def _existing_chunk_hashes(self, db: AsyncSession, document_id: uuid.UUID) -> list[str]:
        """Stored chunk content hashes for ``document_id``, ordered by ordinal."""
        stmt = (
            select(KnowledgeChunk.content_hash)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.ordinal.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _embed_chunks(self, embed: Embedder, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in bounded batches, preserving order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            result = await embed(batch)
            if not result.ok or result.embeddings is None:
                raise IngestionError(result.error or "Embedding request failed.")
            if len(result.embeddings) != len(batch):
                raise IngestionError("Embedding count did not match chunk count.")
            vectors.extend(result.embeddings)
        return vectors

    def _build_chunk(
        self,
        document: KnowledgeDocument,
        chunk: TextChunk,
        vector: list[float],
        content_hash: str,
    ) -> KnowledgeChunk:
        return KnowledgeChunk(
            workspace_id=document.workspace_id,
            agent_id=document.agent_id,
            document_id=document.id,
            ordinal=chunk.ordinal,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            content_hash=content_hash,
            embedding=vector,
        )


knowledge_ingestion_service = KnowledgeIngestionService()
