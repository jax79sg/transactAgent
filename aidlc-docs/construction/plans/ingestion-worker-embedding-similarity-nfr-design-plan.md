# NFR Design Plan — Ingestion Worker Service Unit: Local Embedding-Based Semantic Similarity (Epic 9)

## Genuinely open item
None. One design point worth stating explicitly rather than leaving implicit: **Vector Store collection
setup at worker startup must NOT be fail-fast**, unlike the Postgres migration pattern. Even though Qdrant is
this project's own `docker-compose` service (not a soft, user-managed dependency like oMLX), FR-10 frames the
*entire* embedding subsystem as a soft dependency that must never block the worker's other, unrelated
responsibilities (ingestion runs, backups, recategorization jobs) — so a Qdrant outage at startup is handled
the same soft way as an oMLX outage mid-operation: logged, not fatal. Documented derivation from FR-10, not a
new product decision.

## Decisions
1. **New pattern: No-Retry Immediate Soft-Fail** for both the embedding endpoint call and Vector Store Client
   calls — deliberately different from the existing retry-with-backoff pattern (Drive/Gemini/OpenRouter).
2. **New pattern: Non-Blocking Vector Store Startup** — `ensure_collections()` runs once at worker startup,
   best-effort; a failure is logged and the worker continues (WR-21's fallback chain means every embedding
   call site already tolerates the vector store being unreachable).
3. **Two new logical components**: `EmbeddingClient` (httpx wrapper around the oMLX endpoint) and
   `VectorStoreClient` (qdrant-client wrapper) — both thin, mirroring the existing `GeminiClient`/
   `OpenRouterClient`/`FxRateClient` shape.

## Mandatory Artifacts
- [x] `nfr-design-patterns.md` — updated in place
- [x] `logical-components.md` — updated in place
