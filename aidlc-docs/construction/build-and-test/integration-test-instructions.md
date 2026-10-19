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

---

## Addendum (2026-10-04) — Probable Duplicate Statement Detection (Epic 14): cross-service checks

The scenarios above are live-stack smoke tests. Epic 14 added two checks that need no live stack at all, kept in `integration-tests/` (see its README for the one-time scratch environment):

### Scenario 6: Worker ↔ API ↔ data — the whole removal lifecycle
- **Command**: `python -m pytest integration-tests -q` (a throwaway PostgreSQL via testcontainers; Docker must be running)
- **What it proves**: the worker detects a pair; the API lists it, refuses a stale or wrong confirmation, queues the removal; the worker executes the API's job; the API reports it removed; the next ingestion run recognises the removed copy's file without reading it; override, re-ingestion, and a scan that never re-proposes the file.
- **Result 2026-10-04**: passes. It found one real defect when first run (a stale "found" count), since fixed.

### Scenario 7: Frontend ↔ API contract
- **Command**: `python integration-tests/contract_check_probable_duplicates.py` (exit 1 and a list of mismatches on any difference)
- **What it proves**: field names, required/nullable, enumerated values and all 8 routes with methods agree between `frontend/src/api/{types,duplicates}.ts` and what the API actually sends (100 items).
- **Result 2026-10-04**: passes; shown to fail on a renamed field, enum typos and wrong routes.

### Looking at the new screens without touching the live stack
Used on 2026-10-04 and torn down afterwards: start a throwaway PostgreSQL on a spare port; create the schema and seed it with the real worker code (ingest download-pairs with detection off, run the pair scan, execute one removal, leave one in flight, run again with detection on); run the real API app against it on a spare port with `FRONTEND_ORIGIN` set to the dev frontend's address; run the Vite dev server from a scratch copy of `frontend/` whose `index.html` sets `window.__APP_CONFIG__ = { apiBaseUrl: "http://localhost:<spare port>" }`. **The frontend's default API address is the live API's port, so that override is essential**; confirm in the browser's network log that nothing reaches the live port. Log in through the form (a reload logs you out — a known existing bug, filed separately — so navigate with the app's own links).

### Not run (live-system steps, need a decision)
Rebuild and redeploy; `check-duplicates` against real statements (the CLI migrates the live database to 0019 and 0020 first); switching detection on; the real backfill.

---

## Addendum (2026-10-19) — Account Balance (Epic 13): API Service and Frontend SPA completion

Both remaining units of Epic 13 (API Service, Frontend SPA) were built and each did its own real-data/real-browser verification during Code Generation, in each case against a **dedicated scratch PostgreSQL on a `docker run` container with its own data directory, never the live one and never a bind mount shared with `docker-compose.yml`**:

### Scenario 8: API Service against a read-only dump of the real data
A read-only dump of the live database was restored into a throw-away PostgreSQL (its own container, its own data, deleted afterwards); the real API code ran against it with an anchor entered for each deposit account. **Result**: the service's computed period gaps matched a separately-run independent analysis exactly (28 of 113 statement intervals, including the two under SGD 1); every balance on every printed closing date equalled the statement (125 of 125); an independently written SQL-and-Python recomputation matched 480 of 480 sampled balances; a lookup took 16 ms and the default 12-month series 11 ms (NFR-AB-5's under-one-second target). Full detail: `construction/api-service/code/account-balance-summary.md`.

### Scenario 9: Frontend contract check against real API responses
`api-service/tests/test_contract_fixtures.py` builds a fixed scenario and compares the real API's responses with 11 committed JSON fixtures (`frontend/tests/fixtures/balances/`); `frontend/tests/contract.test.ts` checks the Frontend's own DTO types against the same files. **This is what caught three real places the written API design document had drifted from what was actually built** (the series range's field names, nullable statement ids, and a conversion-unavailable account's own-currency figure) — all corrected in the design documents, none in the code. Regenerate with `UPDATE_CONTRACT_FIXTURES=1 pytest api-service/tests/test_contract_fixtures.py`.

### Scenario 10: Frontend against a scratch stack with invented data
A scratch PostgreSQL (own container, own data), the real `api-service` code, and a `vite build` of the real frontend (served statically) were run on free ports and seeded with 20 accounts covering every state the design describes (anchored and unanchored accounts, a deliberately missing transaction to trigger a discrepancy, two same-named accounts sharing one statement, foreign currency with and without a cached exchange rate, credit cards). Looked at in the built-in browser: dark mode, light mode, 375 px phone width (no horizontal page scroll). **No defects found.** Full detail, including every screen checked: `construction/frontend/code/account-balance-summary.md`.

### Scenario 11: End to end, the real nightly workflow
`frontend/e2e/balances.spec.ts` (new) plus three accounts added to the CI-only `seed_e2e_fixtures.py`, run by dispatching the project's actual nightly e2e GitHub Actions workflow on this feature branch — [run 39107017262](https://github.com/jax79sg/transactAgent/actions/runs/39107017262). All 6 new cases passed, plus the one existing Dashboard case fixed as part of this work; only the pre-existing, unrelated Settings/Transactions spec-drift failures occurred (a separate task has been offered for those, not part of Epic 13).

### Scenario 12 (attempted, not completed — see the warning in `build-instructions.md`)
A real-image, full-`docker-compose` integration check (the actual `api-service` and `frontend` Dockerfiles, nginx's static serving and `config.js` generation, and the real inter-container network, all together, as Scenario 3 above does for the existing app) was attempted and **caused the live `transactagent-db` container to restart** because the isolated copy's database service shared the live `./data/postgres` bind mount by mistake. The live stack recovered with no data loss (confirmed immediately: `pg_is_in_recovery()` false, clean startup log, intact table counts, no errors in the API or worker logs). All scratch containers, images, networks and the scratch compose file were removed. **The user was told immediately and chose to skip retrying this scenario**, relying instead on Scenarios 8–11 above. If you want this scenario run before Operations/deployment, redo it with the database service pointed at its own, non-shared data directory (see the warning in `build-instructions.md`) — it is the one thing about the real built images serving together, through nginx and real inter-container networking, that none of Scenarios 8–11 cover.
