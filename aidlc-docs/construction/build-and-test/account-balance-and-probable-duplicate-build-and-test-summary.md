# Build and Test Summary — Account Balance (Epic 13) and Probable Duplicate Statement Detection (Epic 14)

Both epics ship in one pull request from `feature/account-balance`. All four units are affected: Database (migrations 0019 and 0020), Ingestion Worker, API Service, Frontend. **Nothing was run against the live system, nothing was rebuilt or redeployed, and nothing was committed** — see "What was deliberately not done".

## Build status

| Item | Result |
|---|---|
| Python packages (database, ingestion-worker, api-service) | Install and import cleanly (editable installs in scratch environments) |
| Frontend type-check (`tsc --noEmit`) | Clean |
| Frontend production build (`vite build`, to a scratch directory) | Success: main script 568.0 kB (184.8 kB gzip), stylesheet 20.4 kB. Previous deployed bundle: 548.5 kB, so the new screens cost about 3.6%. The "chunk larger than 500 kB" notice already applied to the old bundle |
| Dependency files | No change to any `pyproject.toml`, `package.json` or lock file by this work; `docker-compose.yml` gained the three duplicate settings on both backend containers |
| Container images | **Not rebuilt** (stop-and-ask item) |

## Unit tests (fresh runs on disposable PostgreSQL 16 containers)

| Unit | Result | Lint |
|---|---|---|
| Database | **188 pass** | `ruff check src tests` clean |
| Ingestion Worker | **664 pass** | clean |
| API Service | **354 pass** (350 before the fix described below, +4) | clean |
| Frontend | **215 pass** (20 files) | `tsc` clean; `eslint` 0 errors, the same 5 pre-existing warnings, none added |
| **Total** | **1,421 pass, 0 fail** | |

Mutation checks recorded at each unit's Code Generation (Worker 7, API 8, Frontend 14, plus 4 on the API fix below) each made a test fail.

## Schema (migrations, real PostgreSQL, throwaway database)

| Script | Result |
|---|---|
| Migration 0019 (Account Balance: accounts, statement accounts, account type) | **43/43**. The first run reported 3 failures: all three asserted that the head revision is 0019, which it no longer is (0020). Stale expectations, not a migration defect; corrected to 0020 and re-run |
| Migration 0020 (probable duplicates) | **80/80** (upgrade, data preserved, downgrade including its refusal when a run file uses the new outcome, re-upgrade, constraints, the byte-order hash CHECK) |

## Integration tests

Two new checks, kept in `integration-tests/` (README there), because each service's own suite fakes the other side:

1. **Frontend ↔ API contract check** — compares what the API actually sends with `frontend/src/api/types.ts` and `duplicates.ts`: **100 items** (field names, required/nullable, enumerated values against the database enums and the service's state strings, and all **8 routes** with their methods). **Passes.** Shown able to fail: a renamed field, enum typos and wrong routes each produce a failure and exit code 1.
2. **Cross-service scenario** — through the real code of the worker and the API against one real PostgreSQL (only Drive, extraction and the vector store faked): two downloads of one statement are ingested; the worker detects the pair; the API lists it with the right labels, counts, keep proposal and preview; refuses a stale correction count and a wrong copy; queues the removal; a repeat is refused; the badge excludes the in-flight pair; the worker executes the API's job; the API reports it removed; the next ingestion run recognises the removed copy's file without reading it, and the API shows "probable duplicate of ..." with the kept statement as the match; the user overrides; the worker re-ingests it; the API reports it ingested at the user's request; a later scan never re-proposes it. **Passes.**

**The scenario found a real defect, now fixed.** The API reported the pair count the last scan had stored, so after a pair was dismissed or removed the panel read "Last checked …; 1 found." beside "No probable duplicate statements." The API now counts pairs awaiting a decision when asked (still null until a scan has completed). Four new tests, each caught by a deliberate mutation (revert to the stored figure; count every status; leave out in-flight pairs; report 0 before any scan). The AR-46 rule carries a dated refinement.

## End-to-end: looked at in a browser

A disposable stack (throwaway PostgreSQL, the real API, worker code used to seed, the dev frontend and later a production build) was used to look at the new screens with realistic data, then torn down. The live stack was untouched (its five containers stayed up and healthy; no request reached the live API port). Seen and as designed: the nav badge, the three panel groups and the information-only pair, the removal confirmation, the in-flight state, the comparison page (removed copy, skipped file, information-only pair), both new outcomes in the run results, the Settings dropdown, dark and light themes, and a 375 px phone viewport. Findings:

- **Fixed:** at phone width the comparison table's Match column (the evidence, in words) was pushed off-screen and amounts were clipped. Each row now spells the marker under its description on narrow screens. One test and two mutation checks guard it; re-checked in the browser.
- **Pre-existing, filed as a separate task (not part of this PR):** a hard reload while signed in logs the user out, on dev and production builds. Cause: the token reaches the API client in a parent effect after children's first requests have gone out unauthenticated. Present on the three existing NavBar queries too; `AuthContext.tsx` and `client.ts` are untouched here.
- **Pre-existing, noted:** a React "unique key" console warning from `IngestionPage`.

Not checked: a real phone; the user's real statements.

## Performance (the matching rule; no load test applies to a one-user app)

| Case | Time |
|---|---|
| Two 300-transaction copies, all distinct keys | 0.7 ms |
| Worst plausible fuzzy case: 40 same-key transactions, every description different | 25 ms |
| A whole pair scan: 200 statements, 4 banks, 4,900 overlapping pairs | 0.12 s |

**Known bound, not changed:** a single group of about 1,100 transactions sharing date, amount, direction and currency, with similar-but-different descriptions, exceeds Python's recursion limit after about 10 s (for dense similar descriptions, 200 take 0.3 s and 600 take 2.9 s; 300 with entirely different descriptions take 1.4 s). Far outside real statements (the calibration over 172 statements averaged 39 transactions each). If it ever happened: the ingestion check fails open (the file is ingested as before, with a warning in the run log); a failed pair scan is logged, stays due, and does not block the embedding backlog.

## Security

- All eight `/duplicates` routes sit behind the existing login (authentication tests on every route).
- A removal needs the hash of the copy **and** the exact correction count the person was shown; a stale or wrong confirmation is refused with a typed 409 and nothing is deleted (in the API suite and the scenario).
- The API never touches the vector store; the worker re-verifies before it deletes. Preview counts use bound parameters.
- No new dependencies, no new secrets, no new external integration. Dependency vulnerability scanning was not run (no scanner is part of this project).

## Existing issues seen, unrelated to this work

- `database/.venv` and `api-service/.venv` in the repository are broken (missing interpreter); scratch environments were used. (`ingestion-worker/.venv` works.)
- The API's import of the Gemini client emits a Pydantic "`any` is not a Python type" warning.
- The reload-logout bug and the React key warning above.

## What was deliberately not done (needs the user's decision)

These stay stopped, as recorded in the standing-instruction interpretation:

1. **Rebuild or redeploy containers.** The running app still serves the old frontend, API and worker.
2. **Run `check-duplicates` (the accuracy check) against the real statements.** The backfill CLI applies migrations at start, so even this read-only check would migrate the live database to 0019 and 0020.
3. **Switch duplicate detection on.** It ships off; the intended order is the accuracy check first.
4. **Run the real backfill** (needs a typed confirmation and a verified backup, and only after the accuracy check passes).
5. **Commit, push, open the pull request.**

Also still open and carried into the final report: the Account Balance Ingestion Worker Code Generation approval and the Database rework gate were passed under the standing instruction rather than by an explicit approval; Account Balance code was edited in place while doing so; the Gemini-versus-local-oMLX categorization provider questions (Q2–Q6) are unanswered.

## Overall status

- **Build**: success. **All tests**: pass (1,421 unit, 1 cross-service scenario, 1 contract check with 100 items, 2 migration scripts, browser review).
- **Ready for Operations**: yes, subject to the five decisions above. None of them has been taken.
