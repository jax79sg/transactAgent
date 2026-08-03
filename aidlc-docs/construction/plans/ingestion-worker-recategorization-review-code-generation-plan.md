# Code Generation Plan — Ingestion Worker Service Unit — Recategorization Review Panel

**Unit**: Ingestion Worker Service (Unit 3). **Stories**: US-6.1, US-6.2, US-6.3.
**Dependencies**: Database unit (complete).

Executed alongside this plan (small, well-scoped change to one existing function), consistent with how this feature's Database unit was handled.

## Steps

1. [x] **Business Logic Generation**:
   - Modified: `ingestion-worker/src/ingestion_worker/config.py` — `recategorization_auto_apply_threshold` setting
   - Modified: `ingestion-worker/src/ingestion_worker/categorization/repository.py` — `find_categorized_transactions_excluding()`, `record_proposal()`
   - Modified: `ingestion-worker/src/ingestion_worker/categorization/service.py` — `recategorize_unsure_from_precedent()` broadened/split (signature changed: now takes `job_id`)
   - Modified: `ingestion-worker/src/ingestion_worker/orchestrator/pipeline.py` — updated call site
2. [x] **Business Logic Unit Testing**:
   - Modified: `ingestion-worker/tests/test_categorization_service.py` — `TestRecategorizeUnsureFromPrecedent` rewritten: 1 existing test's fixture/expectation corrected for the new threshold semantics (real bug in the OLD test's assumption, caught by actually computing the rapidfuzz score rather than assuming the fixture still meant what it used to), 5 new tests added
3. [x] **Documentation Generation**:
   - Modified: `aidlc-docs/construction/ingestion-worker/code/business-logic-summary.md`

## Verification

- [x] Ran `test_categorization_service.py` in isolation: 9/9 passing
- [x] Ran the full `ingestion-worker` unit test suite: 72/72 passing (up from 68 pre-change), no regressions
- [x] Computed real rapidfuzz `token_sort_ratio` scores for every test fixture pair used (not assumed) — this is what caught that the pre-existing test's fixture ("IKEA FURNITURE STORE" vs "...#2", ~93) no longer clears the new 97-point auto-apply threshold, changing what that test needed to assert
