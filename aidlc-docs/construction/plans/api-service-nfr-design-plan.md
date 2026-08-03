# NFR Design Plan — Unit 2: API Service

**Input**: `aidlc-docs/construction/api-service/nfr-requirements/` (approved — FastAPI, JWT auth)

## NFR Design Category Assessment

| Category | Assessment |
|---|---|
| Resilience Patterns | Fail-fast on startup migration error (reused from Unit 1's pattern, applied here since Unit 2 also runs `run_migrations_with_lock()` at startup); a `/health` endpoint (checks DB connectivity) is added so docker-compose/Unit 4 can detect readiness — decided directly, not a user tradeoff |
| Scalability Patterns | N/A — single Uvicorn worker process is sufficient for one user |
| Performance Patterns | Already addressed (Unit 1 indexes, AR-8 pagination); connection pooling uses SQLAlchemy's default pool with a small size (5) appropriate for one user — decided directly |
| Security Patterns | JWT validation as a FastAPI dependency applied to all routes except `/auth/login` and `/health`; **real decision**: CORS policy — question below |
| Logical Components | No new components beyond what NFR Requirements already established (FastAPI app, JWT middleware, DB session-per-request dependency) |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (CORS origin policy) — Answer: A, restrict to configured Frontend origin
- [x] Step 2: Generate `nfr-design-patterns.md`
- [x] Step 3: Generate `logical-components.md`

## Clarifying Question

### Question 1 — CORS Policy
The Frontend SPA (Unit 4) runs as a separate container/origin and will call this API via browser-based `fetch`/XHR, which requires CORS configuration. What policy should apply?

A) **Restrict to the Frontend's configured origin only** (e.g., `http://localhost:3000` or whatever origin/port Unit 4 ends up using, read from an env var) — standard practice, only allows requests from the app's own UI, not from arbitrary websites

B) **Allow all origins** (`*`) — simplest to configure, no risk of misconfiguring the allowed-origin env var breaking the app after a port change, but technically permits any website to make (authenticated-required, so still gated by JWT) requests to the API

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
