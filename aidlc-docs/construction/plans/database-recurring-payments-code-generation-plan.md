# Code Generation Plan — Database Unit — Recurring Payments (Epic 8)

**Unit**: Database (Unit 1). **Scope**: 3 new entities, standalone plus 2 optional edges into `Category`/`Transaction`.

## Steps

1. [x] **Migration**: `models.py` +3 enums (`RecurringPaymentFrequency`, `RecurringPaymentMatchStatus`, `DetectionSuggestionStatus`) +3 models (`RecurringPayment`, `RecurringPaymentMatch`, `DetectionSuggestion`) + relationship edges on `Category`/`Transaction`; migration `0007_recurring_payments.py`
2. [x] **Unit Testing**: `test_models.py` +`TestRecurringPayment` (7 tests: BR-19 both directions, BR-20 both directions, optional category link both ways, default `is_trusted`), +`TestRecurringPaymentMatch` (4 tests: pending, auto_applied, ORM-shape note re: BR-21 being Alembic-only, different-cycle both valid), +`TestDetectionSuggestion` (4 tests: valid, BR-22 duplicate rejected, different patterns valid, optional category) — 40/40 total passing
3. [x] **Documentation**: `models-summary.md` updated

## Addendum (retroactive, during Ingestion Worker Code Generation)

- [x] Found a real gap: no entity backed `isDetectionScanDueNow()`'s due-check (Application Design's `services.md` pseudocode assumed one existed). Added `DetectionScanRun` (write-once, mirrors `BackupRun` minus failure fields), migration `0008_detection_scan_runs.py`, 2 new tests (42/42 total now) — verified live the same way as 0007 (isolated `create_all()` + `alembic stamp` + `upgrade head`, since 0005 remains broken against a fresh DB), including downgrade + idempotent re-upgrade.

## Verification (not deferred to Build & Test — done now, live)

- [x] Full unit suite against a real disposable Postgres (testcontainers): 40/40 passing
- [x] Migration 0007 verified against a separate real disposable Postgres container, in isolation (schema via `create_all()` minus the 3 new tables + `alembic stamp 0006`, then `upgrade head`) — same technique used for 0006, since 0005 remains broken against a fresh DB (pre-existing, out-of-scope, already flagged as task `task_4932abf1`)
- [x] Table shapes and all 3 constraint types (2 CHECK, 1 partial unique index, 1 plain unique) verified directly via `psql \d`
- [x] `alembic downgrade` cleanly drops all 3 tables + all 3 enum types; re-running `upgrade head` twice is a safe no-op
