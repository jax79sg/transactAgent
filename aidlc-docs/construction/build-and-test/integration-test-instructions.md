# Integration Test Instructions

## Purpose
Test interactions between units that per-unit tests can't cover — each unit's own test suite mocks or bypasses the other units (e.g., Unit 2/3's tests never actually run two real processes racing for the migration advisory lock; the frontend's tests mock every API call). This is where those real interactions get verified.

## Setup Integration Test Environment

### 1. Configure Environment
```bash
cp .env.example .env
# Fill in DB_USER/DB_PASSWORD/JWT_SECRET/GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET
# at minimum. GEMINI_API_KEY/OPENROUTER_API_KEY can be placeholder values unless you
# intend to test Scenario 5 (a real ingestion run) with real statements.
```

### 2. Start the Full Stack
```bash
docker compose build
docker compose up -d
docker compose ps   # wait until all 4 services show "healthy"
```

## Test Scenarios

These scenarios were executed for real during the original Build and Test stage (2026-08-01) — see `aidlc-docs/audit.md` for the full history, including 2 real bugs this process found and fixed (an Alembic working-directory bug, an IPv6 healthcheck bug).

### Scenario 1: Database <-> API Service / Ingestion Worker — Migration Race
- **Description**: Both `api-service` and `ingestion-worker` run `alembic upgrade head` at their own startup, guarded by a Postgres advisory lock (NFR Design pattern). Confirms the two processes don't corrupt the schema when racing.
- **Test Steps**: `docker compose up -d`, then immediately `docker compose ps` and watch both backend containers reach `healthy`
- **Expected Results**: All 10 tables present (`docker exec transactagent-db psql -U $DB_USER -d $DB_NAME -c '\dt'`); no errors in either container's logs about `alembic_version` conflicts
- **Cleanup**: None needed — this is just the normal startup sequence

### Scenario 2: API Service — Real Auth Flow
- **Description**: A real login round-trip through the actual HTTP API, not a mocked test client.
- **Setup**: Insert a user with a real bcrypt hash (`docker exec transactagent-api python3 -c "from api_service.auth.security import hash_password; print(hash_password('yourpassword'))"`, then insert via `psql`)
- **Test Steps**: `curl -X POST http://localhost:7878/auth/login -d '{"username":"...", "password":"..."}' -H "Content-Type: application/json"`; take the returned token and call `curl http://localhost:7878/categories -H "Authorization: Bearer <token>"`; then repeat without the header
- **Expected Results**: Login returns a JWT + `expiresAt`; the authenticated call returns `200` (empty array if no categories seeded yet); the unauthenticated call returns `401`
- **Cleanup**: Delete the test user row

### Scenario 3: Frontend <-> API Service — Full Login-Through-Navigation Flow
- **Description**: The actual React app, in a real browser, against the real running `api-service`.
- **Setup**: Same test user as Scenario 2
- **Test Steps**: Open `http://localhost:8787`, log in through the UI, click through NavBar links to Dashboard/Transactions/Ingestion/Settings
- **Expected Results**: All 5 pages (including Login) render without console errors; CORS doesn't block any request (confirms `FRONTEND_ORIGIN` and the frontend's actual origin match exactly)
- **Note**: Use in-app link clicks, not the browser's address bar/back-forward, if testing via an automated browser tool — some automation harnesses don't preserve `sessionStorage` across a tool-driven full-page navigation the way a real user's browser does (this is a tooling artifact, not an app behavior, confirmed during original testing)
- **Cleanup**: Log out or clear the browser's `sessionStorage` for `localhost:8787`

### Scenario 4: Ingestion Worker — Liveness
- **Description**: Confirms the worker's polling loop is actually alive, not just that the container is running.
- **Test Steps**: `docker exec transactagent-worker sh -c "ls -la /tmp/worker-heartbeat"`, wait 10s, repeat
- **Expected Results**: The heartbeat file's modification time updates every ~5s (the poll interval); `docker compose ps` shows `ingestion-worker` as `healthy`

### Scenario 5: Full Pipeline — Google Drive to Dashboard (requires real credentials)
- **Description**: The one scenario this environment could not execute end-to-end (no real Gemini/OpenRouter/Google OAuth credentials available in the original build environment) — you should run this once with your own real credentials before relying on the app.
- **Setup**: Real `.env` values for `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`; at least one real bank statement PDF in the configured Drive folder
- **Test Steps**: Log in to the frontend -> Settings -> "Connect Google Drive" -> complete the Google consent screen -> Ingestion -> "Run Ingestion" -> watch live progress -> Transactions (verify extracted rows) -> Dashboard (verify charts populate)
- **Expected Results**: Run completes with `filesProcessedCount` matching the number of statements in the folder; transactions appear with sensible categories; re-running ingestion with the same files shows `filesSkippedCount` incrementing instead of duplicating data (FR-3)

## Run Integration Tests

There is no separate automated integration-test suite (no CI harness in scope for this personal project) — Scenarios 1-4 above are the repeatable smoke tests; Scenario 5 is a one-time real-credentials validation you run yourself. All 4 are straightforward to re-run manually via the commands given.

## Cleanup
```bash
docker compose down        # stop and remove containers (keeps ./data/postgres)
docker compose down -v     # also remove volumes, for a fully clean slate
rm .env                    # if you created one for testing only
```
