"""Seed Prestyj Batch Video Ads knowledge documents and verify retrieval.

Run from ``backend/`` after the target workspace/agent exists:

    uv run python -m scripts.demo.seed_prestyj_knowledge --env local

By default this targets the deterministic demo workspace/agent from
``scripts.demo.seed_prestyj``. Pass ``--workspace-id`` and ``--agent-id`` to seed any
other Prestyj sales agent. Writes are idempotent: each document is upserted by a
stable seed key in ``knowledge_documents.metadata`` and then re-indexed into
``knowledge_chunks`` for hybrid pgvector + keyword retrieval.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.knowledge_document import KnowledgeDocument
from app.services.ai.embeddings import EMBEDDING_DIM, Embedder, EmbeddingResult
from app.services.knowledge.ingestion_service import (
    IngestionError,
    knowledge_ingestion_service,
)
from app.services.knowledge.knowledge_context_service import knowledge_context_service
from app.services.knowledge.prestyj_batch_video_ads import (
    KNOWLEDGE_SEED_VERSION,
    PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS,
    PRESTYJ_BATCH_VIDEO_ADS_RETRIEVAL_CHECKS,
    KnowledgeSeedDocument,
    RetrievalCheck,
)
from app.services.knowledge.retrieval_service import (
    RetrieveOptions,
    knowledge_retrieval_service,
)
from scripts._harness import (
    EXIT_FAILURE,
    EXIT_OK,
    ExecutionContext,
    bootstrap,
    log_event,
    run,
)
from scripts.demo.seed_prestyj import AGENT_ID as DEFAULT_AGENT_ID
from scripts.demo.seed_prestyj import WORKSPACE_ID as DEFAULT_WORKSPACE_ID

logger = logging.getLogger("seed_prestyj_knowledge")


def _add_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Prestyj knowledge seed")
    group.add_argument(
        "--workspace-id",
        type=str,
        default=str(DEFAULT_WORKSPACE_ID),
        help="Workspace ID to seed. Defaults to the deterministic Prestyj demo workspace.",
    )
    group.add_argument(
        "--agent-id",
        type=str,
        default=str(DEFAULT_AGENT_ID),
        help="Agent ID to seed. Defaults to the deterministic Prestyj iMessage closer.",
    )
    group.add_argument(
        "--force",
        action="store_true",
        help="Re-embed chunks even when document chunks are unchanged.",
    )
    group.add_argument(
        "--embedding-mode",
        choices=("openai", "deterministic"),
        default="openai",
        help=(
            "Use OpenAI embeddings by default. deterministic is local-only for offline "
            "loader/retrieval verification."
        ),
    )
    group.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip sample retrieval checks after seeding.",
    )


async def _get_agent_or_raise(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> Agent:
    agent = (
        await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if agent is None:
        msg = (
            f"Agent {agent_id} was not found in workspace {workspace_id}. "
            "Run scripts.demo.seed_prestyj first or pass the correct IDs."
        )
        raise RuntimeError(msg)
    return agent


async def _seeded_documents_by_key(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> dict[str, KnowledgeDocument]:
    rows = (
        await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.agent_id == agent_id,
            )
        )
    ).scalars()
    documents: dict[str, KnowledgeDocument] = {}
    for document in rows:
        seed_key = (document.metadata_ or {}).get("seed_key")
        if isinstance(seed_key, str):
            documents[seed_key] = document
    return documents


def _metadata_for(seed: KnowledgeSeedDocument, *, embedding_mode: str) -> dict[str, str]:
    return {
        "seed_key": seed.key,
        "seed_version": KNOWLEDGE_SEED_VERSION,
        "source": "prestyj_batch_video_ads_seed",
        "source_url": "https://prestyj.com/batch-video-ads",
        "embedding_mode": embedding_mode,
    }


def _deterministic_vector(text: str) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < EMBEDDING_DIM:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        values.extend((byte - 127.5) / 127.5 for byte in digest)
        counter += 1
    return values[:EMBEDDING_DIM]


async def _deterministic_embedder(texts: list[str]) -> EmbeddingResult:
    return EmbeddingResult(
        ok=True,
        embeddings=[_deterministic_vector(text) for text in texts],
    )


def _embedder_for_mode(mode: str) -> Embedder | None:
    if mode == "deterministic":
        return _deterministic_embedder
    return None


async def _upsert_document(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    seed: KnowledgeSeedDocument,
    existing: KnowledgeDocument | None,
    embedding_mode: str,
) -> tuple[KnowledgeDocument, str]:
    token_count = knowledge_context_service.count_tokens(seed.content)
    if existing is None:
        document = KnowledgeDocument(
            workspace_id=workspace_id,
            agent_id=agent_id,
            title=seed.title,
            doc_type=seed.doc_type,
            content=seed.content,
            token_count=token_count,
            priority=seed.priority,
            is_active=True,
            metadata_=_metadata_for(seed, embedding_mode=embedding_mode),
        )
        db.add(document)
        await db.flush()
        return document, "created"

    existing.title = seed.title
    existing.doc_type = seed.doc_type
    existing.content = seed.content
    existing.token_count = token_count
    existing.priority = seed.priority
    existing.is_active = True
    existing.metadata_ = {
        **(existing.metadata_ or {}),
        **_metadata_for(seed, embedding_mode=embedding_mode),
    }
    await db.flush()
    return existing, "updated"


async def _verify_retrieval(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    checks: tuple[RetrievalCheck, ...] = PRESTYJ_BATCH_VIDEO_ADS_RETRIEVAL_CHECKS,
    embedder: Embedder | None = None,
) -> bool:
    passed = True
    options = (
        RetrieveOptions(
            embedder=embedder,
            top_k=5,
            min_score=0.0,
            vector_weight=0.0,
            keyword_weight=1.0,
            use_mmr=False,
        )
        if embedder is not None
        else None
    )
    for check in checks:
        passages = await knowledge_retrieval_service.retrieve_passages(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            query=check.query,
            top_k=5,
            options=options,
        )
        haystack = "\n".join(passage.content for passage in passages)
        missing = [term for term in check.expected_terms if term not in haystack]
        if missing:
            passed = False
            log_event(
                logger,
                logging.ERROR,
                "retrieval check failed",
                query=check.query,
                missing=missing,
            )
            continue
        log_event(
            logger,
            logging.INFO,
            "retrieval check passed",
            query=check.query,
            expected_terms=check.expected_terms,
        )
    return passed


async def _run(
    ctx: ExecutionContext,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    force: bool,
    skip_verify: bool,
    embedding_mode: str,
) -> int:
    ctx.announce(
        "seed Prestyj Batch Video Ads knowledge",
        workspace_id=str(workspace_id),
        agent_id=str(agent_id),
        document_count=len(PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS),
        force=force,
        verify=not skip_verify,
        embedding_mode=embedding_mode,
    )
    if embedding_mode == "deterministic" and ctx.env.value != "local":
        raise RuntimeError("--embedding-mode deterministic is only allowed with --env local")
    ctx.confirm("upsert Prestyj Batch Video Ads knowledge documents")
    embedder = _embedder_for_mode(embedding_mode)

    async with AsyncSessionLocal() as db:
        await _get_agent_or_raise(db, workspace_id=workspace_id, agent_id=agent_id)
        existing_by_key = await _seeded_documents_by_key(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
        )

        if ctx.dry_run:
            for seed in PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS:
                action = "update" if seed.key in existing_by_key else "create"
                log_event(
                    logger,
                    logging.INFO,
                    "dry-run: would upsert knowledge document",
                    action=action,
                    seed_key=seed.key,
                    title=seed.title,
                )
            return EXIT_OK

        created = 0
        updated = 0
        skipped = 0
        chunks = 0
        for seed in PRESTYJ_BATCH_VIDEO_ADS_KNOWLEDGE_DOCUMENTS:
            document, action = await _upsert_document(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                seed=seed,
                existing=existing_by_key.get(seed.key),
                embedding_mode=embedding_mode,
            )
            try:
                result = await knowledge_ingestion_service.reindex_document(
                    db,
                    document,
                    embedder=embedder,
                    force=force,
                )
            except IngestionError as exc:
                await db.rollback()
                log_event(
                    logger,
                    logging.ERROR,
                    "knowledge document ingest failed",
                    seed_key=seed.key,
                    error=str(exc),
                )
                return EXIT_FAILURE

            created += int(action == "created")
            updated += int(action == "updated")
            skipped += int(result.skipped)
            chunks += result.chunk_count
            log_event(
                logger,
                logging.INFO,
                "knowledge document seeded",
                action=action,
                seed_key=seed.key,
                document_id=str(document.id),
                chunks=result.chunk_count,
                skipped=result.skipped,
            )

        await db.commit()

        verification_passed = True
        if not skip_verify:
            verification_passed = await _verify_retrieval(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                embedder=embedder,
            )

    log_event(
        logger,
        logging.INFO,
        "Prestyj knowledge seed complete",
        created=created,
        updated=updated,
        skipped=skipped,
        chunks=chunks,
        verification_passed=verification_passed,
    )
    return EXIT_OK if verification_passed else EXIT_FAILURE


def main() -> int:
    ctx, args = bootstrap(
        description=__doc__ or "Seed Prestyj Batch Video Ads knowledge.",
        writes=True,
        logger_name="seed_prestyj_knowledge",
        configure=_add_args,
    )
    return asyncio.run(
        _run(
            ctx,
            workspace_id=uuid.UUID(args.workspace_id),
            agent_id=uuid.UUID(args.agent_id),
            force=bool(args.force),
            skip_verify=bool(args.skip_verify),
            embedding_mode=str(args.embedding_mode),
        )
    )


if __name__ == "__main__":
    raise SystemExit(run(main))
