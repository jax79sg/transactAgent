# Build and Test Summary — Recurring Payments, Budget Alerts & Subscription Detection (Epic 8)

Scoped to this feature. The original `build-and-test-summary.md` and its sibling instruction files remain the project's general reference; this document covers what was specifically verified for this change.

## Build Status
- **Build Tool**: Docker Compose (v2)
- **Build Status**: Success — `api-service` and `frontend` rebuilt twice (once for the initial feature code, again after the bulk-import fix below); `ingestion-worker` rebuilt once; `database`'s image is unchanged (schema ships via migration, not image rebuild). All 4 containers reached `healthy`.
- **Build Artifacts**: 3 rebuilt Docker images (api-service, ingestion-worker, frontend)

## Test Execution Summary

### Unit Tests
- **Total new tests**: 15 (Database) + 34 (Ingestion Worker: 13 cycle + 21 service) + 58 (API Service: 15 cycle + 29 service + 14 API) + 11 (Frontend: 3 NavBar + 8 DashboardPage) = 118
- **Full suite results after this feature**: Database 40/40, Ingestion Worker 168/168, API Service 171/171, Frontend 81/81 — all passing, zero regressions
- **Status**: Pass

### Migration Verification (beyond unit tests)
- `alembic upgrade head` run against real, separate disposable Postgres containers for both migration `0007_recurring_payments` and `0008_detection_scan_runs`. Verified table shape and BR-21 (partial unique index)/BR-22 (unique `description_pattern`) constraints via `psql \d`, `alembic downgrade` fully reverses both, re-running `upgrade head` twice is a safe no-op.
- Reused the pre-existing, out-of-scope migration-0005-against-a-fresh-database bug's established workaround (`create_all()` minus the new tables + `alembic stamp` to the prior revision) for isolated verification only — not re-investigated here (already flagged as background task `task_4932abf1`).
- **Live database**: both migrations applied cleanly to the actual running project database via the app's own auto-migrate-with-advisory-lock startup path — `alembic_version` confirmed at `0008`, all 4 new tables (`recurring_payments`, `recurring_payment_matches`, `detection_suggestions`, `detection_scan_runs`) present, no existing tables affected.

### Integration / End-to-End Tests — Live, Against the Real Running Stack and Real Transaction History
Per the standing privacy constraint for this feature (the user's real recurring-payment names/amounts must never be typed into anything that could be committed), all interactive verification used **invented placeholder payments only** ("Gym Membership", "Car Insurance", "Streaming Service") — never the user's real list.

- **Real detection scan, unprompted**: within one poll cycle of redeploy, the live `ingestion-worker` ran its own due detection scan (WR-19) against the real, full transaction history and correctly identified genuine recurring patterns (loan repayments, insurance premiums, a housing loan, subscriptions, recurring transfers) — 128 real `DetectionSuggestion` rows, confirmed via container logs and the live `/recurring-payments/status` endpoint. This is strong validation that the case-insensitive matching and cadence-window logic (WR-16/17/18/19) work correctly against real, messy bank-statement text, not just synthetic test fixtures.
- **API layer**: minted a real JWT via the app's own signing code against the real `users` row (same approach as Epic 6/7). Verified live: create, list, bulk-import (success + partial-failure), and delete against the real running API and real database.
- **Frontend, real browser session**: logged into the actual running app, opened the Recurring Payments Dashboard tab, confirmed the status summary strip, payments table, add-payment form, bulk-import flow, and detection-suggestions list all render real live data correctly. Did **not** click Add/Dismiss on any of the 128 real detected suggestions — both actions are permanent (AR-20, `description_pattern` uniqueness), and acting on them would irreversibly alter the user's real financial tracking data without being asked to.
- **Cleanup**: all 3 placeholder recurring payments created during verification (via API and via the live UI's bulk-import) were deleted afterward; confirmed `GET /recurring-payments` returns `[]` before signing out of the test browser session. No placeholder data, and no real payee data, was left behind or written into any file in this repo.

### One Real Bug Found and Fixed During Live Verification

**Bulk import's per-row isolation (AR-19) was silently bypassed by FastAPI's own request-body validation.** `BulkImportRow.amount`/`due_month`/`due_day` were typed `Decimal`/`int` on the Pydantic schema. A single unparseable value in *any* row (a typo'd amount, or a due-day that a naive `Number()` cast on the frontend turned into `NaN` → `null` in the JSON body) caused FastAPI to reject the **entire request** with a 422 before `bulk_import_recurring_payments`'s per-row `try`/`except` loop ever ran — silently discarding every valid row in the same batch. This directly undermines the exact workflow the feature exists for: pasting a few dozen real recurring payments at once, where a single typo shouldn't cost the other 40 rows.

Reproduced live via `curl` first (confirmed the 422 masked a good row), then fixed:
- `api-service/src/api_service/recurring_payments/schemas.py` — `BulkImportRow.amount`/`due_month`/`due_day` changed to raw `str | None`, so a malformed value can never fail request-body validation before reaching the service layer.
- `api-service/src/api_service/recurring_payments/service.py` — added `_parse_bulk_row_amount`/`_parse_bulk_row_int`, called inside the existing per-row `try`/`except InvalidRecurringPaymentError` block, so a parse failure now becomes a per-row `BulkImportRowFailure` exactly like a frequency/BR-19/BR-20 violation already did.
- `frontend/src/pages/DashboardPage.tsx`'s `parseBulkImportText` — stopped `Number()`-converting `dueMonth`/`dueDay` client-side (the source of the `NaN`→`null` failure mode); now sends the raw trimmed string, letting the backend's own per-row validation produce a clear, isolated error message instead.
- `frontend/src/api/types.ts` — `BulkImportRow.dueMonth`/`dueDay` retyped `string`/`string | null` to match.
- 3 new regression tests added (2 API-service service-layer, 1 API-service endpoint-level) reproducing the exact scenario; re-verified live through the actual browser UI after the fix (typed a bulk-import batch with one deliberately bad row — "Added 1. 1 row(s) failed." with the good row present in the table).

No application-code regressions from the fix: full suites re-run after each change (API-service 171/171, Frontend 81/81), clean `tsc -b` + `vite build`.

### Performance / Security / Contract Tests
- **Performance**: N/A, same rationale as the base project (no performance NFR target for a single-user personal app)
- **Security**: N/A, Security Baseline extension opted out at the original Requirements Analysis; no new secret-handling surface
- **Contract**: Frontend `types.ts` DTOs hand-kept in sync with the Pydantic schemas (including the bulk-import fix above), verified by `tsc -b` passing and by the real browser session rendering real API responses correctly

## Overall Status
- **Build**: Success
- **All Tests**: Pass (460 unit tests across all 4 units — 40 Database + 168 Ingestion Worker + 171 API Service + 81 Frontend — plus live end-to-end verification against the real running stack and real transaction history, including one real bug found and fixed)
- **Ready for Operations**: Yes
