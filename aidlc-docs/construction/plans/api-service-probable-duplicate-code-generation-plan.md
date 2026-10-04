# Code Generation Plan — API Service Unit — Probable Duplicate Statement Detection (Epic 14)

**This plan is the single source of truth for API Service Code Generation of this feature.**

**Unit**: API Service (Unit 2). **Stories**: US-14.1, 14.2, 14.3, 14.4 (the API's side), 14.5, 14.6. **Design source**: `aidlc-docs/construction/api-service/functional-design/` (AR-38..AR-50, endpoint paths fixed at Frontend Functional Design) and the Database design (BR-39..BR-53).
**Dependencies**: Database unit (done); the Ingestion Worker (done) writes what this unit reads and executes what this unit requests.
**Code location**: workspace root, `api-service/` (existing structure; modified in place). Documentation: `aidlc-docs/construction/api-service/code/` (markdown only).
**Branch and delivery**: the existing branch `feature/account-balance`; one PR for Epics 13 and 14. Nothing is committed or pushed.
**Approval status**: passed under the user's standing instruction of 2026-10-04.

## Approach notes (stated up front)

1. **A new component package, `api_service/duplicates/`**, in the layout every other component uses (`router.py`, `service.py`, `repository.py`, `schemas.py`), registered in `main.py` behind the existing router-level login requirement (AR-38).
2. **No matching logic in this unit.** The worker stores the keep-proposal and `removal_allowed`; this unit displays them. The one derived number, `onlyOnRemovedCopy`, is the stored removed-side count minus the stored matched count (AR-41), so there is no copy of the rule to drift.
3. **The removal preview's dependent list must equal the real one (BR-51).** The preview counts the same four dependent kinds the worker deletes. A test computes the dependents from the table metadata and asserts the preview's kinds cover the deleted ones, so a future dependent table fails here too.
4. **Conditional writes, never silent overwrites (AR-50).** Dismissing is a single `UPDATE ... WHERE status = 'pending'`; a race on confirming a removal is caught by the database's one-active-job rule inside a savepoint, so a lost race is a clear 409 and the session stays usable.
5. **Settings**: three catalog entries (the switch as an enumerated `false`/`true`, since the catalog has no boolean type), the lowercase-boolean display fix, and the display-only mirror fields; the catalog grows from 44 to 47 and the two tests that assert the count change with it.
6. **Existing tests must keep passing unchanged** except the two catalog-count assertions, which change by design.

## Steps

1. [x] **Branch**: confirm `feature/account-balance`. Nothing committed or pushed.
2. [x] **Errors** — modify `errors.py`: `PairNotPendingError` (409 `pair_not_pending`), `RemovalNotOfferedError` (409 `removal_not_offered`), `RemovalAlreadyRequestedError` (409 `removal_already_requested`), `StatementMissingError` (409 `statement_missing`), `ConfirmationOutOfDateError` (409 `confirmation_out_of_date`), `NotASkippedFileError` (409 `not_a_skipped_file`); the existing `NotFoundError` for 404.
3. [x] **Schemas** — create `duplicates/schemas.py`: `StatementLabelDTO`, `RemovalPreviewDTO`, `RemovalStatusDTO`, `PairDTO`, `PairPage`, `PendingPairCountResponse`, `RemovalRequest`, `ComparisonRowDTO`, `ComparisonSideDTO`, `ComparisonDTO`, `OverrideResponse`, `ScanStatusDTO`, all `CamelModel` with the enumerated values as the stored snake_case strings (the pair `status` may be `pending`, `removed`, `dismissed` or `superseded`, since dismissing returns the updated pair).
4. [x] **Repository** — create `duplicates/repository.py`: pairs and their latest jobs, the three list groups, the active-job test, statements by content hash, live manual-correction counts, the preview's dependent counts (the worker's predicates), comparisons with rows, remembered files by comparison, the scan-state row, and the run-file label lookup.
5. [x] **Service** — create `duplicates/service.py`: `list_pairs` (the three groups of AR-39, newest first within each, paginated), `get_pending_count` (AR-40), `build_pair` (labels from the stored comparison mapped by `keep_hash`; live counts; stale; preview; latest removal; `removalOffered`), `get_comparison` (AR-45's derived state, `thisFileSide`, `canOverride`), `confirm_removal` (AR-42's ordered checks, one `queued` job, the lost-race mapping), `dismiss_pair` (AR-43), `override_skipped_file` (AR-44, idempotent, the note for a removed copy), `get_scan_status` and `request_recheck` (AR-46).
6. [x] **Router** — create `duplicates/router.py` (prefix `/duplicates`, router-level login) with the eight paths fixed at Frontend design: `GET /pairs`, `GET /pairs/pending-count`, `GET /comparisons/{id}`, `POST /pairs/{id}/remove`, `POST /pairs/{id}/dismiss`, `POST /comparisons/{id}/override`, `GET /scan-status`, `POST /recheck`; register it in `main.py`. (`/pairs/pending-count` is declared before `/pairs/{id}/...` so it is not read as an id.)
7. [x] **Run-file detail** — modify `ingestion/schemas.py` (`RunFileDetail` gains `duplicate_comparison_id` and `matched_statement`), `ingestion/router.py` and `ingestion/service.py`/`repository.py` (resolve the matched side through the comparison and the remembered file, falling back to the earlier side) (AR-47).
8. [x] **Settings** — modify `app_settings/catalog.py` (category "Duplicate Statements"; `duplicate_detection_enabled` standard enum `false`/`true` default `false`; `duplicate_match_ratio` standard float 0.50 to 1.00 default 0.80; `duplicate_min_transactions` advanced int 1 to 50 default 3; the docstring's count), `app_settings/service.py` (`_effective_value_str` renders a bool in lowercase), and `config.py` (the three display-only mirror fields with the worker's defaults) (AR-48).
9. [x] **Tests** — create `tests/test_api_duplicates.py` (real PostgreSQL through the TestClient, the worker's shapes: the UOB and Trust pairs, an information-only different-size pair): authentication on every route; the list's three groups and ordering; the badge count (pending without an active job, information-only included, in-flight excluded); labels from the stored comparison and the worker's keep proposal; live correction counts; the preview's counts and `onlyOnRemovedCopy`; stale pairs; each of AR-42's refusals in order, the exact acknowledged-count guard, the job inserted on success, a double confirmation and a lost race; dismiss (success, not pending, active job, concurrent decided); override (skipped, removed with its note, idempotent, a held pair is `not_a_skipped_file`, unknown 404); the comparison's every derived state and `thisFileSide`; scan status (including `detectionEnabled` from the effective setting) and recheck (creates the single row, idempotent); the BR-51 preview-versus-dependents test. Modify `tests/test_api_ingestion.py` (a probable-duplicate run file returns the comparison id and matched label; other outcomes return nulls), `tests/test_api_settings.py` and `tests/test_settings_validation.py` (47 entries; the three new settings; the switch renders as `false`/`true` and rejects other values; the lowercase-boolean display).
10. [x] **Verification** — the whole API Service suite (the 261 existing plus the new), `ruff check src tests`; a **mutation check** (a scratch copy, one deliberate defect at a time): the exact acknowledged-count guard weakened, the keep-statement-exists check removed, `removal_allowed` ignored, dismiss made unconditional, the badge counting in-flight pairs, the preview missing a dependent kind; each must make a test fail. Re-run the Ingestion Worker and Database suites as a regression check.
11. [x] **Documentation** — create `aidlc-docs/construction/api-service/code/probable-duplicate-summary.md` and update the unit's code README.
12. [x] **Progress** — tick each step, mark the stories' API side `[x]`, update `aidlc-state.md`, confirm via `git status` that only intended files changed and no duplicates exist.

## Story coverage (API side)

| Story | What this unit provides |
|---|---|
| US-14.1, 14.2 | Run-file detail (comparison id, matched label); the comparison endpoint with its derived state |
| US-14.3 | The override endpoint; the comparison's `ingest_at_next_run` and `ingested_at_your_request` states |
| US-14.4 | A remembered file appears in later runs' file lists the same way (the worker writes the run file; this unit reads it) |
| US-14.5 | The pairs list, the badge count, dismiss, scan status and re-check |
| US-14.6 | The removal preview and the confirm endpoint (the worker executes) |

## Completion criteria
- All steps `[x]`; the API Service suite passes (existing tests unchanged apart from the two count assertions); `ruff check src tests` clean; the mutation check shows each safety property guarded by a test; no file duplicated; no change outside `api-service/` and `aidlc-docs/`.

## Completion notes (2026-10-04)

All 12 steps done. 350 API Service tests pass (261 existing + 89 new); `ruff check src tests` clean; eight mutations each caught by a test; the Database (188) and Ingestion Worker (664) suites pass as a regression check. Findings and operator notes are in `aidlc-docs/construction/api-service/code/probable-duplicate-summary.md`.

Differences from the plan as written, all found by running things: an automatic lint fix introduced a runtime bug (`dict(result)`), caught by 23 failing tests; the test module needed its environment set before importing the app; and the catalog asserts its own size at import time, in addition to the two tests.

