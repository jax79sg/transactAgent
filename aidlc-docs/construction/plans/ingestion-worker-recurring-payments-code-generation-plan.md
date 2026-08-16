# Code Generation Plan — Ingestion Worker Service Unit — Recurring Payments (Epic 8)

**Unit**: Ingestion Worker Service (Unit 3). **Stories**: US-8.4, US-8.5, US-8.6.
**Dependencies**: Database unit (`RecurringPayment`/`RecurringPaymentMatch`/`DetectionSuggestion`/`DetectionScanRun` tables) — complete.
**New module**: `ingestion_worker/recurring_payments/` (`cycle.py`, `repository.py`, `service.py`).

## Steps

1. [x] **Config**: 7 new settings (match window, trust tolerance ratio/floor, detection scan interval, detection min occurrences, detection cadence min/max days)
2. [x] **Similarity reuse**: renamed `categorization/similarity.py`'s `_amounts_in_range` to public `amounts_in_range` (NFR-1)
3. [x] **Pure logic**: `recurring_payments/cycle.py` — due-date instance resolution + cycle-period derivation (WR-17)
4. [x] **Repository Layer**: `recurring_payments/repository.py`
5. [x] **Business Logic**: `recurring_payments/service.py` — `match_new_transaction` (WR-16/17/18), `is_detection_scan_due_now`/`run_detection_scan` (WR-19)
6. [x] **Orchestration wiring**: `orchestrator/pipeline.py::_persist_transaction` calls `match_new_transaction`; `main.py::poll_once()` gains the fourth branch
7. [x] **Unit Testing**:
   - `tests/test_recurring_payments_cycle.py` (new, 13 tests)
   - `tests/test_recurring_payments_service.py` (new, 21 tests)
   - `tests/test_main_loop.py` (extended, fourth-branch dispatch)
   - `tests/test_orchestrator_pipeline.py`, `tests/test_similarity.py` (unaffected, re-verified)
8. [x] **Documentation**: `aidlc-docs/construction/ingestion-worker/code/recurring-payments-summary.md`

## Real Issues Found and Fixed During This Stage

- [x] Missing due-check entity for the detection scan — added `DetectionScanRun` to the Database unit (see `database-recurring-payments-code-generation-plan.md` addendum)
- [x] Case-sensitivity bug in the new matcher (mixed-case payment names vs. all-caps transaction descriptions) — found via a real test with realistic input, fixed by uppercasing both sides before scoring

## Verification (not deferred to Build & Test — done now, live)

- [x] Full `ingestion-worker` unit test suite: 168/168 passing, zero regressions
