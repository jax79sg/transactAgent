# Recurring Payment Manager — Code Summary (Epic 8)

New package: [`ingestion_worker/recurring_payments/`](../../../../ingestion-worker/src/ingestion_worker/recurring_payments/).

| File | Purpose |
|---|---|
| `cycle.py` | Pure date-math (WR-17): which due-date instance a transaction belongs to, and the resulting `cycle_period` string |
| `repository.py` | DB access for `RecurringPayment`, `RecurringPaymentMatch`, `DetectionSuggestion`, `DetectionScanRun` |
| `service.py` | `match_new_transaction`, `is_detection_scan_due_now`, `run_detection_scan` — implements WR-16..19 |

## Key implementation decisions

- **Matching is hooked into the existing pipeline, not a new poll branch**: `orchestrator/pipeline.py::_persist_transaction` calls `match_new_transaction` immediately after a transaction is saved — the natural moment, no separate pass over the same data.
- **Detection is `poll_once()`'s fourth branch**, extending Backup Manager's precedent exactly (checked only when no run/job/backup was due that cycle).
- **A real gap found during implementation**: nothing backed `isDetectionScanDueNow()`'s due-check. Added `DetectionScanRun` to the Database unit (write-once, mirrors `BackupRun` minus failure fields) rather than faking it with a non-persisted proxy.
- **Case sensitivity bug found and fixed during testing**: `RecurringPayment.name` is user-entered mixed-case ("Gym Membership") while `Transaction.description` is bank-statement all-caps text. `rapidfuzz.fuzz.token_sort_ratio` is case-sensitive (score 18.75 vs. 87.5 for the same pair, case-normalized) — the existing categorization call site never hit this since it only ever compares two already-bank-statement-cased descriptions against each other. Fixed by uppercasing both sides before scoring in `match_new_transaction`.
- **`categorization/similarity.py`'s `_amounts_in_range` was renamed to public `amounts_in_range`**, since `service.py` reuses it directly for the WR-18 trust/tolerance check (NFR-1) — confirmed no external reference to the private name before renaming, full `test_similarity.py` suite re-run to confirm.
- **Candidate selection never gates on amount** (WR-16) — only the auto-apply decision does (WR-18), per FR-5's explicit "amount is a loose guide" requirement.

## Tests

- `tests/test_recurring_payments_cycle.py` (new): 13 tests covering month/year boundary cases and clamping for short months
- `tests/test_recurring_payments_service.py` (new): 21 tests covering matching (window, similarity, live-match dedup, trust/tolerance both directions, annual), detection scan due-check, detection scan pattern criteria, and the pure helper functions
- `tests/test_main_loop.py`: extended with the fourth-branch dispatch priority (3 new/modified tests)
- `tests/test_similarity.py`: unaffected by the private→public rename (12/12 still passing)

Full suite: 168/168 passing (up from 133).
