# NFR Design Patterns — Unit 2: API Service

## Pattern: Fail-Fast Startup Migration (reused from Unit 1)

Same pattern as Unit 1's NFR Design: `run_migrations_with_lock()` is called as the first line of the FastAPI app's startup, before the app begins accepting requests. Any migration failure raises and crashes the container rather than serving against a stale/half-migrated schema.

## Pattern: CORS Restricted to Configured Frontend Origin

**Category**: Security (resolves Question 1 = A)

FastAPI's `CORSMiddleware` is configured with `allow_origins=[FRONTEND_ORIGIN]`, where `FRONTEND_ORIGIN` is read from an environment variable (e.g., `http://localhost:3000`, finalized once Unit 4's Infrastructure Design picks the actual port). `allow_credentials=True` (needed if the JWT is ever carried via cookie rather than header — decided in Code Generation), `allow_methods` and `allow_headers` scoped to what the API actually needs (`GET, POST, PUT, DELETE` and `Authorization, Content-Type`).

## Pattern: JWT Auth as a FastAPI Dependency

A reusable `get_current_user` FastAPI dependency validates the `Authorization: Bearer <token>` header on every route except `/auth/login` and `/health`, raising `401` on missing/invalid/expired tokens (AR-1). Applied via FastAPI's dependency-injection system (`Depends(get_current_user)`), not manual per-route checks, so it can't be accidentally omitted from a new route without an explicit opt-out.

## Pattern: Database Session Per Request

A FastAPI dependency yields a SQLAlchemy `Session` scoped to a single request (opened at request start, committed/rolled back and closed at request end), using SQLAlchemy's default connection pool (pool size 5 — decided directly, appropriate for one user's request concurrency).

## Pattern: Health Endpoint

`GET /health` — no auth required, executes a trivial `SELECT 1` against the database, returns `200 {"status": "ok"}` or `503` if the DB is unreachable. Used by docker-compose's healthcheck (finalized in Infrastructure Design) and by Unit 4's own startup ordering.

## Pattern: Centralized Error Handling

A FastAPI exception handler maps all business-rule violations (AR-1 through AR-10, each raised as a typed exception in the business logic layer) to the consistent `ErrorResponse` shape from `domain-entities.md`, with the appropriate HTTP status code (400/401/404/409) — avoiding ad-hoc error formatting scattered across route handlers.

## N/A Categories (justified)

- **Scalability Patterns**: N/A — single-user, single Uvicorn worker process is sufficient
- **Resilience Patterns beyond fail-fast**: N/A — no external service calls happen synchronously in this unit's request path (Drive/LLM/OCR/FX calls all live in Unit 3, invoked asynchronously)
