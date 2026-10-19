# Build and Test Summary — Account Balance (Epic 13): API Service and Frontend SPA Completion

Epic 13's Database and Ingestion Worker units were built 2026-10-02/03. This stage completes the epic: the **API Service** unit (accounts and balances endpoints) and the **Frontend SPA** unit (the Balances tab) were designed, built and tested 2026-10-18/19, on `feature/account-balance-completion` (PR #50). **Epic 13 is now functionally complete across all four units.** Nothing was rebuilt or redeployed and nothing was merged — see "What was deliberately not done".

## Build status

| Item | Result |
|---|---|
| `api-service` image (`docker compose build api-service`) | Builds cleanly; `hypothesis` added to the editable install's test extra only, nothing in the runtime image |
| `frontend` image (`docker compose build frontend`) | Builds cleanly; bundle 642 kB minified (was 598 kB; +44 kB for the whole feature). The "chunk larger than 500 kB" notice is pre-existing |
| `tsc -b`, `eslint .`, `vite build` | All clean; `eslint` unchanged at its 5 pre-existing warnings |
| `ruff check src tests` (API Service) | Clean |
| Dependency files | `api-service/pyproject.toml` and `uv.lock` gained `hypothesis` (test only); no change to any other lock file |
| Container images | **Not rebuilt against the running deployment** (stop-and-ask item, unchanged from Epic 13's usual pattern) |

## Unit tests

| Unit | Result | Touched by this stage? |
|---|---|---|
| Database | **262 pass** | No (confirmed unaffected, re-run) |
| Ingestion Worker | **734 pass** | No (confirmed unaffected, re-run) |
| API Service | **725 pass** (713 before this stage's one new contract test file, +12) | Yes (built 2026-10-18) |
| Frontend | **651 pass** (327 existing unchanged + 324 new) | Yes (built 2026-10-18/19) |
| **Total** | **2,372 pass, 0 fail** | |

Mutation checks: **45 of 45** on the API Service (20 pure-module, 25 services/repositories/routers/CORS); **25 of 25** on the Frontend, run once and recorded honestly — two of the first-picked mutations turned out to be poorly chosen (one unreachable because of the component's own reset logic, one invisible to the test tool's render batching) and were replaced with better ones rather than counted as false catches. Full detail in each unit's code summary.

## Integration tests

Per-unit scratch-database checks (never the live data, never a path shared with the running deployment):

1. **API Service against a read-only dump of the real data** — the service's computed discrepancies and 480 sampled balances matched an independent recomputation exactly; a lookup took 16 ms (target: under 1 second, NFR-AB-5).
2. **Frontend ↔ API contract check** — a new API test compares real endpoint responses against 11 committed fixtures, and the Frontend checks its own types against the same files. **Found and corrected three places the written API design document had drifted from the built API** (the series response's `start`/`end` field names, nullable discrepancy statement ids, and the own-currency figure still shown for an `fx_unavailable` account) — all three were documentation errors; the code and its tests were right throughout.
3. **Frontend against a scratch stack with invented data** — 20 accounts covering every state the design describes, looked at in the built-in browser in dark mode, light mode and at 375 px phone width. No defects found.
4. **End to end** — `balances.spec.ts` (new) run against the project's real nightly e2e workflow, dispatched on this branch ([run 39107017262](https://github.com/jax79sg/transactAgent/actions/runs/39107017262)). All 6 new cases passed, plus the one existing Dashboard case fixed in this stage; only the pre-existing, unrelated Settings/Transactions spec-drift failures occurred.

**One integration check was attempted and not completed: see "An incident, disclosed" below.**

## Performance

Verified in the API Service's live-data check (above): a balance lookup 16 ms, the default 12-month series 11 ms, a 12-month daily series 32 ms, discrepancies 11 ms — all against the current data volume (about 7,000 transactions, 20 accounts), well inside NFR-AB-5's under-one-second target. No load test applies (a one-user app).

## Security

- Every new endpoint sits behind the existing login (tested: 401 without one).
- Typed, stable error codes for every refusal (AR-64); no silent failure.
- A replaced anchor and a merge are each one conditional write/transaction; a lost race is an explicit error, never a silent overwrite.
- No new dependency beyond `hypothesis` (test-only), no new secret, no new external integration.

## An incident, disclosed

While attempting a real-image, full-`docker-compose` integration check (building the actual `api-service` and `frontend` images and bringing up an isolated copy of the stack with remapped container names and ports), the isolated `database` service's `./data/postgres` bind mount — a relative path — resolved to the **same host directory the live `transactagent-db` container was already using**. Postgres, started from the isolated container, detected the live process's lock file as invalid from its own perspective and forced an immediate shutdown, which **crashed the live database container** (it recovered automatically via `restart: unless-stopped`; about 12 seconds of downtime).

**Verified immediately afterward, before anything else was done**: the live container restarted cleanly (`pg_is_in_recovery()` false, a clean startup log, no crash-recovery warnings); table counts are consistent with the real data (7,230 transactions, 188 statements, 20 accounts, 56 categories, 1 user); no errors appear in the API or worker container logs around the incident; all five live containers are healthy and the live API and frontend answer normally. The user was told plainly before any further work continued. Every scratch container, image, network, volume and compose file from the attempt was removed.

**The user was asked how to proceed and chose to skip retrying this one check**, relying instead on the four integration checks listed above, each of which used a properly isolated data directory. The attempt and its root cause are documented in `build-instructions.md`'s addendum as a warning, and the untried scenario is recorded in `integration-test-instructions.md`'s addendum (Scenario 12) in case it is wanted later, with the fix stated (give the isolated database its own, non-shared data directory).

## What was deliberately not done (needs the user's decision)

1. **Rebuild or redeploy containers.** The running app still serves the previous frontend and API; none of Epic 13's screens or endpoints are live yet.
2. **Add the two new settings to `.env.example` and `docker-compose.yml`'s `api-service` environment block.** `reporting_time_zone` and `balance_mismatch_tolerance` have code-level defaults, so the API runs without this, but it should be done before deployment so they are overridable the same way every other API-owned setting is.
3. **The real-image `docker-compose` integration check** (Scenario 12 above), given the incident.
4. **Repair the pre-existing Settings/Transactions e2e spec drift**, found while verifying Step 14 — unrelated to this feature; a separate task has been offered and not acted on.
5. **Merge the PR.**

## Overall status

- **Build**: success for both new units' images.
- **All tests**: pass (2,372 unit tests across all four units; the integration and contract checks above; the dispatched real nightly e2e run).
- **Ready for Operations**: yes, subject to the five decisions above. None of them has been taken.
