# NFR Requirements Plan — Ingestion Worker Service Unit: Local Embedding-Based Semantic Similarity (Epic 9)

## Genuinely open item
None requiring a new user question. Per user instruction ("continue all the way unless you have questions
I'll need to answer"), the vector DB product choice (NFR-2) is made and documented here — a reversible,
self-hosted OSS pick with a clear rationale, same treatment this project has given comparable single-container
infra picks (e.g. `postgres:16-alpine`) rather than a product-affecting decision. Flagged for correction if
wrong.

## Decisions

1. **Vector DB product (NFR-2): Qdrant** (`qdrant/qdrant` official image). Evaluated against this project's
   established minimal-footprint preference (no separate broker; DB-polling over Redis) balanced against
   genuine ANN/filtering needs (FR-2, WR-21's `excludeEntityId` filter, two collections):
   - **Qdrant**: single self-contained binary/container, no external dependencies (no etcd/object-store side
     services), native cosine similarity, native per-point metadata filtering (needed for `excludeEntityId`),
     mature official Python client (`qdrant-client`), REST+gRPC.
   - **Chroma**: lighter still, but its production/filtering story is less mature and it's more commonly run
     embedded-in-process than as a standalone service — a worse fit for a service shared cleanly across worker
     restarts via a dedicated container.
   - **Milvus**: full ANN feature set but its standard deployment needs etcd + object storage (MinIO) as
     sidecars — directly contradicts the established minimal-footprint precedent for a personal-scale,
     single-user app with a low transaction volume.
   - Qdrant is the only one of the three that's both a single extra `docker-compose` service and has
     first-class filtering — chosen for that combination, not because ANN performance matters at this scale
     (it doesn't, transaction volume here is in the thousands, not millions).
2. **Embedding endpoint client**: `httpx` (already a transitive dependency via this unit's existing HTTP
   clients), calling the user-managed oMLX endpoint's OpenAI-compatible-style embeddings route (exact request
   shape confirmed against oMLX's docs at Code Generation). New config: `EMBEDDING_BASE_URL`,
   `EMBEDDING_MODEL` (default `embeddinggemma-300m`) — kept in their own config namespace, separate from
   `OPENROUTER_*`, since this project already runs a *different* oMLX instance/model
   (`gemma-4-12B-it-4bit`, swapped in for `OPENROUTER_BASE_URL` on 2026-08-01 per `tech-stack-decisions.md`)
   for categorization-LLM-fallback text generation — the embedding model is a distinct process/likely a
   distinct port on the same host, not assumed to be the same running instance.
3. **No retry on the embedding call** (diverges from the Drive/Backup retry-with-backoff pattern, matches the
   existing Gemini/OpenRouter "no cross-provider retry" philosophy, WR-7/WR-25): a single attempt with a short
   timeout (5s, tunable), soft-failing immediately on any error class — retrying would only delay the
   already-fast fuzzy-text fallback for no real benefit at this feature's soft-dependency framing (FR-10).
4. **Tunable values** (all config, deferred-exact-value-at-Code-Generation precedent, e.g. `similarity_threshold`):
   `EMBEDDING_SIMILARITY_THRESHOLD` (cosine, 0.0-1.0 scale — distinct scale from the existing 0-100 fuzzy
   score, default `0.75`, to be sanity-checked against real data during Build and Test same as the original
   `similarity_threshold=85.0` was), `EMBEDDING_TOP_K` (default `5`, WR-23), `EMBEDDING_BATCH_SIZE` (default
   `50`, WR-26), `EMBEDDING_DIMENSIONS` (default `768`, `embeddinggemma-300m`'s native output size — Qdrant
   requires a fixed vector size at collection-creation time; configurable in case a deployment truncates via
   Matryoshka representation).

## Mandatory Artifacts
- [x] `nfr-requirements.md` — updated in place (addendum)
- [x] `tech-stack-decisions.md` — updated in place (addendum)
