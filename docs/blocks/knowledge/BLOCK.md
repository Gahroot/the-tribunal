---
id: knowledge
name: Knowledge Base (RAG Retrieval)
tier: C
status: manifest
summary: Per-workspace knowledge base with document ingestion, chunking, embeddings, and hybrid (pgvector KNN + tsvector keyword) retrieval — the RAG layer the AI agent queries for grounded answers and the knowledge-search tool.
owns_paths:
  - backend/app/services/knowledge/
  - backend/app/api/v1/knowledge_documents.py
  - backend/app/models/knowledge_document.py
  - backend/app/models/knowledge_chunk.py
  - frontend/src/components/knowledge/
public_api:
  - backend/app/api/v1/knowledge_documents.py::router
  - backend/app/services/knowledge/ingestion_service.py::KnowledgeIngestionService
  - backend/app/services/knowledge/retrieval_service.py::KnowledgeRetrievalService
  - backend/app/services/knowledge/knowledge_context_service.py::knowledge_context_service
  - backend/app/services/knowledge/search_tool.py::execute_knowledge_search
  - frontend/src/components/knowledge/knowledge-base-page.tsx
depends_on: [core, agent-brain, automations, offers]
external_integrations: [openai]
env_vars: []
db_tables:
  - backend/app/models/knowledge_document.py::knowledge_documents
  - backend/app/models/knowledge_chunk.py::knowledge_chunks
alembic_migrations: shared linear chain — knowledge_documents (79a0808ae761_add_human_profile_knowledge_docs_), knowledge_chunks (b546d7e401fe_rag_chunks_pgvector — requires the pgvector extension and creates the vector(1536) + generated tsvector columns).
workers: []
extraction_effort: medium
extraction_notes: Knowledge depends on agent-brain for embeddings at the model layer — knowledge_chunk.py imports EMBEDDING_DIM and ingestion/retrieval import Embedder/embed_texts — so the embedding model/dimension is a hard coupling: the stored vector(1536) column must match agent-brain's embedder. Also requires Postgres with the pgvector extension; a plain Postgres target will fail the chunks migration.
---

## Overview

Knowledge is the RAG layer. Operators upload documents per workspace; the block extracts text, chunks it, embeds the chunks, and stores them for retrieval. `knowledge_chunks` uses a hybrid index — a `vector(1536)` pgvector column for semantic KNN plus a generated `tsvector` column for keyword search — so retrieval blends semantic and lexical matching. The AI agent queries this layer two ways: `knowledge_context_service` injects grounding context into prompts, and `execute_knowledge_search` is exposed as an agent tool. Ingestion emits `EVENT_KNOWLEDGE_DOCUMENT_UPLOADED` on the automation bus so uploads can trigger workflows.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- `backend/app/models/knowledge_chunk.py:32: from app.services.ai.embeddings import EMBEDDING_DIM`; `backend/app/services/knowledge/ingestion_service.py:36 & retrieval_service.py:33: from app.services.ai.embeddings import Embedder, embed_texts` → **agent-brain** — the embedding model and dimension. This is a model-level coupling: the `vector(EMBEDDING_DIM)` column is sized by agent-brain's constant.
- `backend/app/services/knowledge/prestyj_batch_video_ads.py:13: from app.services.offers.prestyj_batch_video_ads import PRESTYJ_BATCH_VIDEO_ADS_PACKAGE_OPTIONS, PRESTYJ_BATCH_VIDEO_ADS_SOURCE_URL, format_price` → **offers** — seeds a demo/vertical knowledge set from offer data.
- `backend/app/api/v1/knowledge_documents.py:21: from app.services.automations.events import EVENT_KNOWLEDGE_DOCUMENT_UPLOADED, emit_automation_event` → **automations** — sanctioned automation-bus hook (keep, don't sever).

Core: `app.api.deps` (`DB`, `CurrentUser`, `get_workspace`), `app.db.pagination.paginate`, `app.db.base.Base`, `app.db.session.transaction_boundary`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/knowledge-documents` (`knowledge_documents.router`) — upload, list, delete documents.
- Services consumed by other blocks: `knowledge_context_service` and `execute_knowledge_search` (both imported by agent-brain's roleplay, text response generator, and tool executors to ground the agent), plus `KnowledgeIngestionService` / `KnowledgeRetrievalService`.
- Frontend: `knowledge/` (`knowledge-base-page` — upload + document management UI).

## How to Extract

1. Pull `core` plus `agent-brain` (embeddings), `automations` (event hook), and `offers` (demo seed) transitively. `agent-brain` is non-negotiable — without the embedder, chunks can't be created or queried.
2. Provision **Postgres with the pgvector extension** (`pgvector/pgvector:pg17` locally); a plain Postgres target fails the `b546d7e401fe_rag_chunks_pgvector` migration.
3. Copy `owns_paths` (knowledge service, the router, two model files, the frontend tree).
4. Sever imports: inject an embedder port (agent-brain) — but keep `EMBEDDING_DIM` aligned with the stored column, or re-embed; repoint the offers demo seed; keep the `emit_automation_event` hook if the bus comes along.
5. Set `OPENAI_API_KEY` for embeddings (the call itself routes through agent-brain's `embeddings.py`); no knowledge-specific env vars.
6. Port `knowledge_documents` and `knowledge_chunks` and their creating revisions.
7. No workers to register.

## Risks

- **Embedding dimension lock:** `vector(1536)` is sized by agent-brain's `EMBEDDING_DIM`; changing the model/dim during extraction invalidates every stored embedding and requires a full re-ingest.
- **pgvector dependency:** the chunks table needs the pgvector extension and a generated tsvector column; targets without pgvector cannot run the migration or KNN queries.
- **Hard agent-brain coupling at the model layer:** the model file itself imports from agent-brain, so knowledge cannot even import cleanly without agent-brain present (unlike service-only couplings).
- **OpenAI cost/availability:** ingestion and retrieval both call the embeddings API; rate limits or outages stall ingestion and degrade retrieval to keyword-only.
- **Tenancy:** documents and chunks are workspace-scoped; ensure retrieval filters by workspace so one tenant's KB never leaks into another's grounding context.
