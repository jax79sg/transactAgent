# Tech Stack Decisions — Unit 3: Ingestion Worker Service

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Reused from Unit 1 |
| Google Drive access | `google-api-python-client`, `google-auth` | Official Google libraries; reads refresh token from `oauth_credentials`, handles access-token refresh internally |
| Extraction LLM | **Google Gemini** via `google-genai`; model **configurable via `GEMINI_MODEL` env var** (2026-08-01 per user request — no model ID hardcoded), defaulting to `gemini-3.5-flash-lite` (confirmed via Google's docs to accept Text/Image/Video/Audio/PDF input and support structured outputs — any override must also support image input, since this call always sends page images). **Changed from `gemini-3.1-flash-lite` on 2026-08-02**: that model consistently transposed day/month for at least one bank's day-first-printed dates (OCBC); switch verified via 3 live extraction runs against the real failing statement showing 0 invalid dates on gemini-3.5-flash-lite vs. a consistent ~50% failure rate on gemini-3.1-flash-lite — see aidlc-docs/audit.md | Clarification 1a = C (hybrid) — Gemini for extraction specifically, needs reliable vision/PDF support |
| Categorization LLM fallback | `openai` package pointed at a configurable `base_url` (`OPENROUTER_MODEL`/`OPENROUTER_API_KEY`/`OPENROUTER_BASE_URL` env vars). Originally OpenRouter's `openrouter/free` router; **swapped 2026-08-01 to a locally-hosted omlx-server instance** (`gemma-4-12B-it-4bit`, reached via `host.docker.internal:8000` since omlx-server runs on the host Mac, not in a container) after hitting OpenRouter free-tier rate limits (429s) during real ingestion runs | Clarification 1a = C — text-only, lower-stakes, worth trying free-tier first; base_url made configurable specifically so the provider itself is swappable without code changes |
| Cross-provider retry | **None** (Clarification 1b = B) | A failure at either LLM call is terminal for that statement/transaction within the run — no silent fallback to the other provider |
| PDF-to-image | `pdf2image` (+ `poppler-utils` in Docker image) | NFR Requirements Question 2 = B |
| Similarity matching | `rapidfuzz` (`token_sort_ratio`) | Functional Design Question 3 = A |
| FX rate fallback API | `exchangerate.host` | Clarification 2b = B — only called when a statement doesn't print its own SGD-converted amount |
| ORM / migrations | SQLAlchemy, Alembic (`transactagent_db.migrate.run_migrations_with_lock()`) | Reused from Unit 1 |
| PBT framework | **Hypothesis** | Standard Python PBT library; applies to similarity matching, currency-conversion source-priority resolution, extraction-response schema validation round-trip (Partial PBT mode) |
| Test framework | pytest + testcontainers | Matches Units 1/2 |
| Worker loop | Simple polling (5s interval, `asyncio` sleep loop or a lightweight scheduler) — no message broker | Consistent with Application Design's "keep it simple" decision |

## Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9)

| Decision | Choice | Rationale |
|---|---|---|
| Vector DB | **Qdrant** (`qdrant/qdrant` image, `qdrant-client` Python SDK) | Evaluated against minimal-footprint precedent vs. genuine ANN/filtering needs — see `ingestion-worker-embedding-similarity-nfr-requirements-plan.md` for the full Qdrant vs. Chroma vs. Milvus comparison |
| Embedding endpoint client | `httpx`, pointed at `EMBEDDING_BASE_URL` (new, separate config from `OPENROUTER_BASE_URL`) | The categorization-LLM-fallback oMLX instance already running (`gemma-4-12B-it-4bit`) is a different model/likely a different port than the embedding model (`google/embeddinggemma-300m`, FR-1) — kept as an independent config value rather than assumed-shared |
| Embedding call retry | **None** — single attempt, 5s timeout, immediate soft-fail (WR-25) | Diverges from the Drive/Backup retry-with-backoff pattern on purpose; matches the existing no-cross-provider-retry philosophy (WR-7) — a soft-dependency (FR-10) gains nothing from retrying before falling back to the already-fast fuzzy-text path |
| New tunables | `EMBEDDING_SIMILARITY_THRESHOLD=0.75`, `EMBEDDING_TOP_K=5`, `EMBEDDING_BATCH_SIZE=50`, `EMBEDDING_DIMENSIONS=768` | Defaults set here, to be sanity-checked against real data during Build and Test — same precedent as the original `similarity_threshold=85.0` |

## Package Dependency on Unit 1

Installs the `database/` package (Unit 1) as a local editable dependency, same pattern as Unit 2.
