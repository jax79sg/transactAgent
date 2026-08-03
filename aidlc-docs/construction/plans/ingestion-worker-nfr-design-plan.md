# NFR Design Plan — Unit 3: Ingestion Worker Service

**Input**: `aidlc-docs/construction/ingestion-worker/nfr-requirements/` (approved)

## NFR Design Category Assessment

| Category | Assessment |
|---|---|
| Resilience Patterns | Fail-fast startup migration (reused pattern). **Real decision**: same-provider retry/backoff for transient LLM API errors — question below (distinct from WR-7's "no cross-provider retry", which is already settled) |
| Scalability Patterns | N/A — single worker process |
| Performance Patterns | N/A beyond what's already decided (5s polling, no additional caching needed beyond the FX rate cache already in Unit 1's schema) |
| Security Patterns | API keys via env vars (NFR-4.1); Drive refresh token read-only access from `oauth_credentials` — no additional pattern |
| Logical Components | Worker Loop/Scheduler, thin client wrappers per external API (Gemini, OpenRouter, Google Drive, exchangerate.host) — decided directly below |

## Direct Decisions

- **Worker loop**: a simple `asyncio` loop — sleep 5s, poll for a queued `IngestionRun` or `RecategorizationJob`, process it fully (or skip if none), repeat. No task queue library needed at this scale.
- **Logical components**: `GeminiClient`, `OpenRouterClient`, `DriveClient`, `FxRateClient` — each a thin wrapper around its respective SDK/HTTP call, isolating the external dependency so business logic (`categories/service.py`-equivalent in this unit) doesn't call SDKs directly.

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (same-provider retry/backoff strategy) — Answer: A, up to 3 attempts, exponential backoff from 2s
- [x] Step 2: Generate `nfr-design-patterns.md`
- [x] Step 3: Generate `logical-components.md`

## Clarifying Question

### Question 1 — Same-Provider Retry on Transient Errors
WR-7 already settled that a failure does NOT fall back to a *different* LLM provider. But should a single transient error (e.g., a rate-limit response, a network timeout) from the *same* provider be retried a few times before giving up, or treated as an immediate terminal failure?

A) **Retry with backoff** (e.g., up to 3 attempts, exponential backoff starting at 2s) against the same provider before marking the statement/transaction as failed/`UNSURE` — more resilient to the transient rate-limit blips that are common with free-tier APIs (OpenRouter) and shared quotas (Gemini)

B) **No retry** — any error, transient or not, immediately marks the statement/transaction as failed/`UNSURE`; you'd need to re-trigger ingestion manually if a transient blip caused failures

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
