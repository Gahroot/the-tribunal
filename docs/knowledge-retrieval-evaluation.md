# Knowledge retrieval quality

## Retrieval path

Both voice and text `search_knowledge` executors use the shared knowledge search
service. This checkout already uses pgvector cosine retrieval plus indexed
Postgres English FTS, reciprocal rank fusion (RRF, k=60), and MMR diversity
reranking. This is the local, provider-free ranking option, not a hosted semantic
cross-encoder. No Voyage/Cohere credentials or new dependencies are required.

This update makes the lexical arm match **any** normalized question term rather
than requiring every word of a spoken question to appear in the answer. English
stemming and stopword removal still happen in PostgreSQL. Input is tokenized,
bounded to 64 terms, and passed as a bound SQL value. Both retrieval arms and
parent expansion retain workspace, agent, and active-document restrictions.

An injected reranker now sees the over-fetched shortlist before the final top-k
cut, allowing it to promote an answer outside the original top-k. Candidate
counts are bounded. The default remains RRF + MMR.

Ingestion is synchronous through `knowledge_documents.py` and
`KnowledgeIngestionService`, not a dedicated knowledge worker. Existing
`chunk_sections` creates offset-preserving children inside Markdown sections;
retrieval expands hits into bounded parent context. Heading-less documents use
recursive paragraph/line/word splitting. There is no model-generated context.
Existing rows remain searchable without a backfill. Section-aware splitting
applies when documents are reindexed; this change does not rewrite live data.

The embedding model remains `text-embedding-3-small` with explicit
`dimensions=1536`, matching `vector(1536)`. A different model, even at the same
dimension, requires a complete re-embedding rollout before switching queries;
mixing embedding spaces would invalidate similarity. No migration is needed.

## Real-call evaluation (pending)

Do not interpret synthetic regression tests as retrieval hit-rate evidence.
Real-call measurement is deferred: the configured loopback database was offline
and no reviewed JSONL question set was available during implementation.

Prepare a private JSONL file from actual mid-call pricing/policy questions:

```json
{"workspace_id":"<uuid>","agent_id":"<uuid>","query":"<anonymized actual question>","expected_document_id":"<uuid>","expected_text":"<verbatim answer excerpt>","category":"pricing"}
```

Use `pricing` or `policy`. Label against the knowledge base applicable to the
call; exclude caller names, phone numbers, and other personal information.
Include paraphrases, exact amounts, product names, policy exceptions, and short
follow-up questions. Keep the dataset outside git. Labels must refer to an
active document in the specified workspace and agent.

Run against a reachable matching database with embedding credentials:

```sh
cd backend
PYTHONPATH=. uv run python scripts/eval_knowledge_retrieval.py --cases /private/cases.jsonl --top-k 5
```

The evaluator validates labels before embedding, uses a read-only transaction,
and shares one query embedding across both modes. Dense baseline disables FTS
and MMR; hybrid uses FTS + RRF + MMR. Both modes use the same parent expansion,
so this comparison isolates ranking rather than claiming a chunking A/B test.
Embedding failure aborts instead of artificially depressing the dense baseline.

Output is aggregate-only, overall and by category:

- Document hit@k: expected document appears in returned passages.
- Answer hit@k: a passage from that document actually contains the answer excerpt.
- MRR: reciprocal rank of the first expected-document passage, averaged over cases.

Record dataset size, top-k, knowledge snapshot, and both mode outputs before
calling the real-call requirement complete. No measured improvement is claimed
yet. PostgreSQL runtime verification also remains pending; this checkout has
client binaries but no running server or installed `postgres` executable.

## Corpus research

The standalone `steroids` executable was unavailable. The Steroids corpus tool
was used instead, refreshing the already-indexed `mastra-ai/mastra` repository.
`embedders/voyageai/src/reranker.ts` at `b7f9616e` demonstrates batch candidate
reranking followed by a top-k selection and mapping returned indices back to
input documents. That ordering informed the shortlist correction here; no
upstream code or new hosted provider was copied into this proprietary project.
