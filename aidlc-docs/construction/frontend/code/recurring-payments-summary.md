# Recurring Payments — Code Summary (Epic 8)

New/changed files under [`frontend/src/`](../../../../frontend/src/).

| File | Purpose |
|---|---|
| `api/types.ts` | New DTOs: `RecurringPaymentFrequency`, `RecurringPaymentStatus`, `RecurringPaymentDTO`, `RecurringPaymentCreateRequest`, `RecurringPaymentUpdateRequest`, `BulkImportRow`, `BulkImportRowFailure`, `BulkImportResponse`, `RecurringPaymentRef`, `RecurringPaymentMatchDTO`, `DetectionSuggestionDTO`, `RecurringPaymentsStatusSummaryDTO` |
| `api/recurringPayments.ts` | New module — one function per API Service endpoint (CRUD, bulk import, match approve/reject, suggestion dismiss/add, status summary) |
| `components/NavBar.tsx` | Added `RecurringPaymentsBadge` — polls `getRecurringPaymentsStatus` every 5 min (matching `BackupStatusPanel`'s cadence), shown on the Dashboard nav link, hidden at zero |
| `pages/DashboardPage.tsx` | Added a 4th tab, "Recurring Payments" (`RecurringPaymentsTab`) — status summary strip, payments table with status badges, add-one form, bulk-import textarea, pending-matches review list, detection-suggestions triage list |

## Key implementation decisions

- **Badge excludes `dueSoonCount` by design**: nothing has gone wrong yet for a due-soon item, so it doesn't compete for the user's attention the way an overdue payment, a pending match, or a new detection suggestion does. Matches the reasoning already documented for `PendingReviewBadge`.
- **Bulk import is plain-text, one row per line**: `parseBulkImportText()` accepts `Name, Amount, Frequency, DueDay` (monthly) or `Name, Amount, Frequency, DueMonth, DueDay` (annual) — chosen over a file-upload/CSV flow since the volume this feature targets (dozens of rows, entered once) doesn't justify the extra UI surface.
- **All new interactive elements carry `data-testid`s** (`new-recurring-payment-*`, `add-recurring-payment-button`, `bulk-import-*`, `approve-match-{id}`, `reject-match-{id}`, `add-suggestion-{id}`, `dismiss-suggestion-{id}`, `recurring-payment-row-{id}`, `status-badge-{status}`, and the three empty-state ids) to keep the new tab covered by the same test-first approach used elsewhere in this app.

## Bug found and fixed during Code Generation

- **Test-only bug, not a product bug**: the first draft of `DashboardPage.test.tsx` asserted mutation calls with `toHaveBeenCalledWith(id)`, but TanStack Query v5 invokes `mutationFn(variables, context)` — a second `{ client, meta, mutationKey }` argument the app code never asked for and never uses. Fixed by asserting on `spy.mock.calls[0][0]` instead of the full call. No application code changed.
- **Test isolation bug caught before it could mask failures**: the dashboards-API mocks (`getCategoryTrends`/`getCashFlow`/`getBankBreakdown`) were originally installed via a plain function call at `describe`-body scope instead of inside `beforeEach`, so `afterEach`'s `vi.restoreAllMocks()` wiped them after the first test — later tests were silently falling through to the real (network-less, failing) implementation. Fixed by moving the setup into a proper `beforeEach`.

## Tests

- `tests/NavBar.test.tsx` — extended with a new `describe("NavBar recurring payments badge")` block: 3 tests (hidden at zero, shows combined overdue+pending+suggestion count, `dueSoonCount` alone never shows the badge).
- `tests/DashboardPage.test.tsx` (new — this page had zero prior coverage): 8 tests covering both empty states, a populated payment row with its status badge, the add-payment form submission, approve/reject on a pending match, add/dismiss on a detection suggestion, and bulk-import parsing/submission.

Full frontend suite: **81/81 passing** (up from 70). `tsc -b` and `vite build` (production build) both clean.
