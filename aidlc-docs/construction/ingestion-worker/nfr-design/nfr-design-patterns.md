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

## N/A Categories (justified)

- **Scalability Patterns**: N/A — single worker process, single personal user
- **Performance Patterns**: N/A beyond what's already decided — LLM API latency dominates and isn't something to further optimize for a manually-triggered personal workflow
