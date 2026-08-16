# NFR Design Patterns — Unit 3: Ingestion Worker Service

## Pattern: Fail-Fast Startup Migration (reused from Units 1/2)

Same pattern: `run_migrations_with_lock()` called before the worker loop starts.

## Pattern: Same-Provider Retry With Backoff

**Category**: Resilience (resolves Question 1 = A)

Each external LLM call (Gemini extraction, OpenRouter categorization) is wrapped with up to **3 attempts**, exponential backoff starting at **2 seconds** (2s, 4s, 8s), retrying only on transient error classes (HTTP 429 rate-limit, HTTP 5xx, network timeout/connection errors) — never retrying on a definitive error (e.g., HTTP 401 auth failure, HTTP 400 bad request), since those won't succeed on retry. After 3 failed attempts, the call is terminal (WR-1 extraction failure / WR-4 UNSURE categorization) — still no cross-provider fallback (WR-7).

## Pattern: Worker Polling Loop

A simple `asyncio` loop: sleep 5s (NFR Requirements Question 6 = A), check for one queued `IngestionRun` or `RecategorizationJob`, fully process it if found (never processing two concurrently — WR-8), repeat. No task queue library (Celery, RQ, etc.) — unnecessary complexity at this scale, consistent with Application Design's "keep it simple" decision.

## Pattern: Per-File and Per-Transaction Failure Isolation (reused from NFR-2.2)

Already captured in Functional Design's pipeline (business-logic-model.md) — one file's extraction failure doesn't abort the run; the pattern here just confirms the retry-with-backoff above happens *inside* that per-file try/except boundary, not around the whole run.

## Pattern: No-Retry Immediate Soft-Fail (added 2026-08-13 — Local Embedding-Based Semantic Similarity, Epic 9)

**Category**: Resilience (deliberately diverges from "Same-Provider Retry With Backoff" above)

The embedding endpoint call (`EmbeddingClient`) and every Vector Store Client call are wrapped in a single
try/except with a short timeout (5s) and **zero retries** — any exception (timeout, connection error, HTTP
error, non-2xx response) is caught and treated as "no embedding available for this call" (WR-25), falling
through to the existing fuzzy-text path immediately. This is intentional, not an oversight: FR-10 frames the
entire embedding subsystem as a soft, optional enhancement — retrying would only add latency to a call whose
failure already has a fast, correct fallback, unlike Gemini/OpenRouter where a failure is genuinely terminal
for that statement/transaction (WR-1/WR-4).

## Pattern: Non-Blocking Vector Store Startup (added 2026-08-13 — Epic 9)

Unlike the fail-fast Postgres migration pattern above, `VectorStoreClient.ensure_collections()` (creating the
`transactions`/`recurring_payment_names` Qdrant collections if they don't exist, called once at worker
startup) is **best-effort**: a failure is logged and the worker proceeds to its normal polling loop. Even
though Qdrant is this project's own `docker-compose` service (not a user-managed external dependency like
oMLX), FR-10's soft-dependency framing applies to the whole embedding subsystem, not just the oMLX call — a
Qdrant outage must not block the worker's unrelated responsibilities (ingestion runs, backups,
recategorization jobs, detection scans). Every embedding call site already tolerates the vector store being
unreachable via the same WR-25 soft-fail path.

## N/A Categories (justified)

- **Scalability Patterns**: N/A — single worker process, single personal user
- **Performance Patterns**: N/A beyond what's already decided — LLM API latency dominates and isn't something to further optimize for a manually-triggered personal workflow
