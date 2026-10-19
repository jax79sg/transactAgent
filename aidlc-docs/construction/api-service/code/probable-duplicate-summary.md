# Probable Duplicate Statement Detection — API Service Code Summary (Epic 14)

Design: `../functional-design/` (AR-38..AR-50; endpoint paths pinned at Frontend Functional Design) and the Database design (BR-39..BR-53). Plan: `aidlc-docs/construction/plans/api-service-probable-duplicate-code-generation-plan.md`.

## What was built

| Area | Where | What |
|---|---|---|
| Router | `duplicates/router.py`, registered in `main.py` | Eight routes under `/duplicates`, all behind the existing login: `GET /pairs`, `GET /pairs/pending-count`, `GET /comparisons/{id}`, `POST /pairs/{id}/remove`, `POST /pairs/{id}/dismiss`, `POST /comparisons/{id}/override`, `GET /scan-status`, `POST /recheck` |
| Logic | `duplicates/service.py` | The panel's three groups (in flight, pending, removed in the last 24 hours; AR-39); the badge count (AR-40); labels from the stored comparison mapped by the worker's `keep_hash`; live correction counts; the removal preview; the comparison's derived state and `thisFileSide`; confirming a removal (AR-42's ordered checks, then one `queued` job); dismissing; overriding; scan status and re-check |
| Queries | `duplicates/repository.py` | Pairs, latest jobs, active-job tests, statements by hash, live counts, the preview's counts (the worker's predicates), comparisons with rows, remembered files |
| DTOs | `duplicates/schemas.py` | `PairDTO`, `RemovalPreviewDTO`, `RemovalStatusDTO`, `ComparisonDTO` and its sides and rows, `OverrideResponse`, `ScanStatusDTO`, and the requests |
| Errors | `errors.py` | `pair_not_pending`, `removal_not_offered`, `removal_already_requested`, `statement_missing`, `confirmation_out_of_date`, `not_a_skipped_file` (all 409) |
| Run results | `ingestion/{schemas,router,service}.py` | `RunFileDetail` gains `duplicateComparisonId` and a structured `matchedStatement`; the matched side is found through the remembered file, not by position |
| Settings | `app_settings/{catalog,service}.py`, `config.py` | Three catalog entries in a new "Duplicate Statements" category (the switch as an enumerated `false`/`true`, default `false`); the catalog is **47** entries; booleans display in lowercase; the display-only mirror fields |

**What it does not do**, by design: it holds no copy of the matching rule (the worker stores the keep proposal and `removal_allowed`; the API displays them), it never calls the worker or the vector store, and it deletes nothing: confirming a removal inserts a job row that the worker re-verifies and executes.

## How it was tested

**350 API Service tests pass** (261 existing + 89 new) and `ruff check src tests` is clean. The 261 existing tests pass unchanged except the two catalog-count assertions (44 to 47), which change by design. The Database (188) and Ingestion Worker (664) suites were re-run as a regression check and pass.

New tests are in `tests/test_api_duplicates.py`, against a real PostgreSQL through the real app: authentication on every route; the three list groups and their order; the badge count; labels from the stored comparison and the worker's proposal shown even when it is the later hash; live correction counts; the preview's counts with a dependent of every kind; `onlyOnRemovedCopy`; information-only and stale pairs; every refusal of confirming a removal and their order, the exact acknowledged-count guard (lower and higher both refused), a retry after a failed job, a lost race; dismiss (success, decided, in flight, and a decision made meanwhile is never overwritten); every comparison state; override (skipped, removed with its note, idempotent, held pair, unknown); scan status and re-check; the run-file detail; the settings entries and their bounds; and a metadata-based test tying the preview's dependent kinds to the real dependents of a statement (BR-51).

**Mutation check** (a scratch copy of the code, one deliberate defect at a time; every one made a test fail): the acknowledged-count guard weakened to "live is greater than shown"; the "both statements still exist" check removed; `removal_allowed` ignored when confirming; dismiss made unconditional; the badge counting pairs with a removal in flight; a dependent kind dropped from the preview; the lowercase-boolean display fix removed; the lost-race mapping (the savepoint) removed.

## Findings made while building and testing

1. **`dict(result)` does not work on a SQLAlchemy result.** An automatic lint fix replaced a dict comprehension with `dict(rows)`, which failed at runtime ("not subscriptable") and showed up as 23 failing tests; it is `dict(rows.all())`. (The same pattern in the worker's repository was already over a list, so it was unaffected.)
2. **The API test module must set its environment before importing the app.** The existing tests set the required variables inside a fixture and import lazily; a module-level import fails at collection. The new module sets the same defaults at the top, with the lint exemption stated.
3. **Two jobs created in one test transaction share the database's `now()`**, so "the latest removal job" is ambiguous in a test (in production each request is its own transaction). The test sets the retry's `requested_at` explicitly.
4. **Settings entry count**: the catalog also asserts its own size at import time (`assert len(SETTINGS_BY_NAME) == 44`), in addition to the two tests, so a mismatch fails every test at collection; it is now 47.
5. **(Found at Build and Test, 2026-10-04.) `pairsFound` went stale after a decision.** The status reported the count the last scan had stored, so after the user dismissed or removed the only pair the panel showed "1 found" beside "No probable duplicate statements." A cross-service scenario (worker detects, API lists and queues, worker removes, API reports) exposed it. Fixed: the API now counts pairs awaiting a decision when asked (`repository.count_pending`), still null until a scan has completed. Four new mutation-checked tests replace one (354 API tests now pass: 350 + 4); AR-46 carries the dated refinement.

## Operator notes

- The three new settings reach this container through `docker-compose.yml` (done with the Ingestion Worker unit) so the Settings page shows the real deployed value. The switch is changed on the Settings page, which writes the shared override file; the worker reads it when it restarts.
- A removal requested in the app is executed by the worker within a poll cycle; the panel polls while one is in flight.
