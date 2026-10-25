# Business Logic Model — Unit 4: Frontend SPA

Client-side logic beyond simple "call an endpoint and render the response."

## Session Lifecycle (AuthProvider)

- **On app load**: read token from `sessionStorage`; if present and not obviously expired (compare `expiresAt` to now), treat as logged in optimistically — the next API call will `401` if it's actually invalid, at which point the session is cleared.
- **Sliding expiry** (Unit 2 NFR Requirements Question 2 = A): every successful authenticated API response may carry a refreshed token (exact transport — response header vs. body field — finalized in Code Generation matching Unit 2's actual implementation); if present, the frontend updates its stored token so continuous use never logs the user out.
- **On 401 from any API call**: clear session state and `sessionStorage`, redirect to `/login`. Centralized in a single API-client wrapper (an interceptor/fetch-wrapper) so this logic exists once, not duplicated per API call site.

## Ingestion Run Polling Lifecycle

- **Trigger**: `POST /ingestion/runs` -> on success (`202`), immediately start polling `GET /ingestion/runs/{runId}` every 3 seconds.
- **Poll loop termination**: stops as soon as `status` is `completed`, `completed_with_failures`, or `failed` — never polls indefinitely.
- **Page navigation during a run**: if the user navigates away from `/ingestion` while a run is active and comes back, `ActiveRunProgress` re-derives "is a run active" from `GET /ingestion/runs` (most recent entry) rather than relying on in-memory state that would've been lost — so an in-progress run is never "forgotten" by the UI.
- **409 on trigger**: rather than treating this as a hard error, the frontend uses the `existingRunId` in the response body to immediately start polling that run instead — the user's click still results in seeing live progress, just for the already-running run.

## Filter/Group State <-> URL Mapping

- All `TransactionsPage` filter/group/sort/page state is serialized to the URL query string (e.g., `/transactions?category=Groceries&dateFrom=2026-01-01`) and deserialized from it on page load — this makes filtered views bookmarkable/shareable and is what makes dashboard drill-down (below) work via simple navigation rather than passing state through application memory.
- Changing any filter control updates the URL (without a full page reload) and triggers a new `GET /transactions` call with the updated query params.

## Dashboard Drill-Down (US-4.5)

- Clicking a chart segment (a specific category+month, or bank+month) constructs a `/transactions` URL with `category`/`bank` and a `dateFrom`/`dateTo` pair spanning that segment's month, then navigates there — reusing the same URL-driven filter state described above rather than a separate drill-down-specific code path.

## CSV Export

- Reuses the exact current `TransactionFilterBar` state (minus pagination) to construct the `GET /transactions/export.csv` request — guaranteeing "what you see is what you export" (US-3.6).

## Category Whitelist Cache

- The active-category list (used to populate every category `<select>` across the app — correction dropdown, add/rename forms) is fetched once per session and cached client-side, invalidated (refetched) after any add/rename/remove action on `SettingsPage` — avoiding a redundant `GET /categories` call before every single inline correction.

## Pending Review Badge Polling (added 2026-08-02 — Epic 6)

- `PendingReviewBadge` polls `GET /recategorization/proposals/pending-count` every 30 seconds, regardless of which page is active (mounted once at `NavBar`, not per-page) — deliberately much looser than the Ingestion 3-second poll: that poll is watching one specific run the user just triggered and is actively waiting on, while this is an ambient "is there anything waiting" indicator nobody is staring at in real time. 30s keeps the badge reasonably fresh without adding meaningful load for a single-user app.
- Any successful approve/reject/bulk-approve/bulk-reject action on `ReviewPage` immediately invalidates the pending-count query (React Query cache invalidation) rather than waiting for the next 30s tick — so the badge updates instantly for actions the user just took, and only relies on polling to catch changes from elsewhere (e.g. a new correction generating fresh auto-applied/pending proposals via the next ingestion-worker poll cycle).

## Backup Status Panel Polling (added 2026-08-08 — Epic 7)

- `BackupStatusPanel` polls `GET /backups/status` every 5 minutes, mounted only on `ReviewPage` (unlike `PendingReviewBadge`, this isn't shown in the nav, so it only needs to be fresh while that page is open). Looser than `PendingReviewBadge`'s 30s deliberately: a backup outcome changes at most once a night (WR-11/BR-17 — at most one `BackupRun` row per day), so sub-minute freshness has no value here, unlike the pending-proposal count which can change every few seconds as ingestion runs land.
- No cache-invalidation trigger exists for this query (unlike the pending-count badge, which invalidates on approve/reject) — nothing on the Frontend ever writes a `BackupRun` row, so there's no local action that could make the cached status stale ahead of the next poll.

## Recurring Payments Badge and Tab (added 2026-08-08 — Epic 8)

- The Dashboard nav badge polls `GET /recurring-payments/status` on the same 5-minute cadence as `BackupStatusPanel` (a status that changes at most daily doesn't need sub-minute freshness) and shows only when `overdueCount + pendingMatchCount + newSuggestionCount > 0` — the same "hide entirely at zero, no zero-count clutter" precedent `PendingReviewBadge` already established. `dueSoonCount` deliberately isn't part of the badge trigger: nothing has gone wrong yet for a due-soon item, so it shouldn't compete for the user's attention the way an overdue bill or a pending decision does.
- Approving/rejecting a match or dismissing/adding a detection suggestion on the Dashboard tab immediately invalidates both the recurring-payments list query and the status-summary query (React Query cache invalidation) — same "don't wait for the next poll tick for the user's own actions" reasoning as `PendingReviewBadge`.

## Review Selection State (added 2026-08-02 — Epic 6)

- `ReviewPage` holds a `Set<proposalId>` of the current page's selected rows, reset whenever the page number or the underlying proposal list changes (e.g. after a bulk action removes resolved rows) — never carried across pages, consistent with `BulkActionBar`'s "acts on the current page" scope (frontend-components.md).
- "Select all" toggles every row on the current page in one action; unchecking any individual row after "select all" simply removes it from the `Set`, it does not need a separate "partial selection" mode.

## Transaction Embedding Badge (added 2026-08-13 — Local Embedding-Based Semantic Similarity, Epic 9)

- Purely derived from `TransactionDTO.embeddingStatus`, already present in every `GET /transactions` response — no separate query, no polling (contrast the Pending Review/Backup Status/Recurring Payments badges above, all of which poll on an interval specifically because they surface something actionable that changes independently of the page the user is looking at). A transaction's badge simply reflects whatever the list query last returned, and updates the next time that query runs (a filter change, a manual refetch, or a page navigation) — acceptable staleness per FR-6's async/eventually-consistent framing, the same reasoning already applied worker-side.
- No cache-invalidation hook is added anywhere for this — unlike `PendingReviewBadge`'s "invalidate after the user's own action" pattern, there is no user action in this unit that changes `embeddingStatus` (it's written exclusively by the Ingestion Worker Service).

## Duplicate Badge and Panel: Polling and Refresh (added 2026-10-04 — Probable Duplicate Statement Detection, Epic 14)

- **Badge**: `PendingDuplicatesBadge` polls `GET /duplicates/pairs/pending-count` every 30 seconds, regardless of the active page (mounted once at `NavBar`), for the same reason `PendingReviewBadge` does: it is an ambient "is anything waiting" indicator nobody is watching in real time. Any action in the panel invalidates the count immediately, so the badge updates at once for what the user just did.
- **Panel list**: `GET /duplicates/pairs` is fetched when the panel mounts and after each of the user's own actions. **While any listed pair has a removal in flight** (queued, running, or cleaning up embeddings) it refreshes every **3 seconds**, the same as the Ingestion page's active-run poll, because the user has just asked for it and is waiting; it stops as soon as none is in flight. Otherwise it does not poll: the API's other panels do not, and the badge already catches changes from elsewhere.
- **Scan status**: `GET /duplicates/scan-status` is fetched with the panel and refreshed with the list. It drives the header line ("Last checked …") and the two idle messages ("switched off" and "none found"). **Check again** posts the re-check and shows "Re-check requested" until the next refresh; it does not wait for the worker.
- **Refresh set**: remove, dismiss, override, and Check again invalidate the pair list, the pending count, and the scan status together, so the three never disagree on screen.

## Removal Flow (added 2026-10-04 — Epic 14)

```
user clicks "Remove duplicate…" on a pair where removalOffered is true
  -> RemovalConfirmDialog opens, showing pair.preview (counts, embeddings, only-on-this-copy, corrections lost)
  -> Cancel: nothing happens
  -> Delete permanently: POST /duplicates/pairs/{id}/remove  { removeStatementHash, acknowledgedCorrectionsLost }
        success: dialog closes; the pair now shows removal "queued"; the panel polls every 3 s until it shows "Removed" (or a failure reason)
        409 confirmation_out_of_date | pair_not_pending | removal_not_offered | statement_missing | removal_already_requested:
              dialog closes; list, count and status refresh; a plain message says what changed; NOTHING was deleted
        other error: message shown in the dialog; the user can retry or cancel
```
The dialog never sends numbers other than the ones it displayed, which is what the API's out-of-date check compares. A removal that fails in the worker leaves the pair pending with its reason, and the same action is available again (a retry).

## Override Flow (added 2026-10-04 — Epic 14)

```
ComparisonPage shows "Not a duplicate — ingest it" when canOverride
  state skipped:  one click -> POST /duplicates/comparisons/{id}/override
  state removed:  first click shows an inline warning; second click -> the same POST
success: the comparison is re-read; the banner reads "Will be ingested on the next ingestion run" (or "Ingested at your request" once it has been)
failure: duplicateErrorMessage shown on the page
```
Overriding does not start ingestion; it takes effect on the next run (A-PD-4), which is why the banner links to the Ingestion page.

## Statement Labels and Periods (added 2026-10-04 — Epic 14)

One helper builds every label so the Ingestion results, the panel and the comparison read the same: "<file name> (<bank>, <period>)", falling back to "<bank> (<period>)" and then "a statement (<period>)". A period is "2 Jun to 30 Jun 2026" within one year and "28 Dec 2025 to 3 Jan 2026" across two. Month names are written out in the helper rather than read from the browser's locale, so the text is identical on every machine and in the tests.

## Responsive, Theme, and Accessibility Rules (added 2026-10-04 — Epic 14)

Every new element carries its dark-mode classes. Tables scroll horizontally inside their container instead of overflowing the page. The comparison's two panels sit side by side on wide screens and stack on narrow ones. Buttons and links keep a comfortable touch size. Status is always conveyed in words as well as colour (the row markers, the banners, the badge's accessible label). The confirmation uses the app's existing modal dialog, which traps focus and restores it on close.



---

# Epic 13 — Account Balance at a Point in Time (Addendum 2026-10-18)

*Behaviour behind the screens in `frontend-components.md` (Epic 13 sections). Answers: Q1 = A (a Balances tab), Q2 = A (combined + 7 largest + Other), Q3 = A (summary line, details on request), Q4 = A (Accounts section with dialogs), Q5 = A (no badge). Everything here is the Frontend's own behaviour; the arithmetic is the API's and is never repeated here.*

## Balances: Opening the Tab and Finding "Today" (Epic 13)

- Four independent reads start together when the tab opens: the lookup (`GET /balances`), the chart (`GET /balances/series` with no dates, so the API supplies the last 12 months ending today), the discrepancies, and the account list. Each part shows its own loading and failure state; one failing never blanks the others.
- A lookup needs a date, and the API refuses one after "today" in its reporting time zone. The first lookup therefore uses the **browser's local calendar date** (`localToday()`, built from the local year, month and day; **not** `toISOString()`, which would give yesterday's date in Singapore before 08:00), with `autoLookup = true`.
- If the API answers **`date_in_future`** while `autoLookup` is true (the browser's clock is ahead of the reporting time zone), the screen silently retries **once** with the day before and shows no error. A second refusal is shown like any other. The first successful answer sets `serverToday` from the response's `today`, and every later success refreshes it; from then on the date input's `max`, the Today button and the dialogs' default date use `serverToday`, never the browser.
- Any change the user makes sets `autoLookup = false`. Switching from Date to Month selects the month of the current result; switching from Month to Date selects the result's resolved date, so the view does not jump.
- The ingested-through line is read from every response (FR-AB-14), so it always matches the figures beside it.

## Balances: Queries, Refresh, and Invalidation (Epic 13)

- Query keys: `["accounts","list"]`, `["balances","lookup",{date|month}]`, `["balances","series",{from,to,granularity}]`, `["balances","discrepancies"]`.
- **No polling.** Balances change only when the owner acts or an ingestion run lands; React Query's refetch on mount and on window focus is enough, and the ingested-through line tells the owner how current the data is.
- **Every successful write invalidates both `["accounts"]` and `["balances"]`** (prefix match), so a new balance, a rename, a retype or a merge shows in the table, the chart, the warnings and the account list together, and cached lookups for other dates are not served stale. Cancelling a dialog invalidates nothing.
- A 4xx answer is not retried (it would only repeat); a network or 5xx failure is retried by React Query's default. While a lookup for a new date loads, the previous result stays, dimmed, rather than flashing empty.
- One write at a time: while a save, rename, retype or merge is in flight every account action is disabled, so two writes cannot race from one screen.

## Balance Entry Flow (Epic 13, US-13.3)

1. Opened from a row's **Set balance** or **Change balance** (balances table) or **Set / Change balance** (accounts section) for a deposit account only (amended for issue #57: the table row used to offer nothing once a balance existed, and the accounts-section button was named Replace balance). For a first balance the date starts at the last date entered in this visit, else `serverToday`, else the browser's date. For an account that already has a balance, the amount starts as that balance (selected) and the date as its own date, so a correction is an edit and the balance does not move to another date unless the owner changes it.
2. The owner types a balance and a date. `parseAmountInput` accepts "1234.5", "1,234.50", "-12.3" and spaces; it refuses empty text, letters, an exponent, and more than two decimals ("never rounded for you") with a message beside the field. A date after `serverToday` is refused the same way. Nothing is sent while either is invalid.
3. **Save** sends `PUT /accounts/{id}/anchor` with the canonical two-place string and the date. On success: close, set the status line (new: "Saved SGD 1,500.00 for 18 Oct 2026."; replacing: "Replaced SGD 1,234.00 (5 Oct 2026) with SGD 1,500.00 (18 Oct 2026)." from `AnchorResponse.previous`), invalidate.
4. **Save and next account** does step 3, then opens the dialog for the next deposit account with no balance (`nextAccountNeedingBalance`, list order), the date carried over and the balance empty; with none left it just closes. Offered only while some other deposit account has no balance.
5. A refusal from the API (`invalid_anchor_value`, `anchor_date_in_future`, `anchor_date_out_of_range`, `not_a_deposit_account`, `account_not_found`) appears in the dialog as a plain sentence; nothing changed; the owner can fix and resubmit. `account_not_found` also refreshes the list and closes the dialog.

## Merge Flow (Epic 13, US-13.2)

1. Opened on the account to be **absorbed**. The candidates to keep are the other accounts with the **same currency** (the API refuses different currencies, `merge_currency_mismatch`; the screen simply does not offer them).
2. On choosing the account to keep, the preview is built from the two list entries and states: counts moved, which name stays, that later matching statements follow, any change of type, and that it cannot be undone. **Type rule (mirrors the API's AR-54)**: the kept account keeps its own type, unless its type was not set by the owner and the absorbed account's was, in which case the owner's choice wins; `mergeTypeOutcome` implements exactly this and a test pins it to the same cases the API tests use.
3. **Balances**: both have one — the owner must choose which to keep (two radios, none preselected; Merge stays disabled until chosen); one has — it is kept and the preview says so; neither — nothing to choose.
4. **Merge** sends `POST /accounts/{keptId}/merge` with `{absorbedAccountId, keepAnchorFrom?}`. On success: close, status line "Merged “A” into “B”.", invalidate. Every refusal (`merge_appear_together`, `merge_currency_mismatch`, `merge_anchor_choice_required`, `merge_anchor_choice_invalid`, `merge_same_account`) is shown in the dialog in plain words with the dialog still open and **nothing changed** (the API makes a merge all-or-nothing). `merge_appear_together` adds "if they look alike, rename them" because that is the owner's real situation with the two same-named GXS accounts.

## Rename and Change Type (Epic 13, US-13.2)

- Both are `PATCH /accounts/{id}` with exactly the one field being changed. Rename trims, requires 1 to 255 characters, and is disabled when unchanged. Change type is disabled when unchanged; the dialog explains the consequence before the owner confirms (leaving *deposit* removes the account from balances, totals, charts and warnings at once but **keeps the entered balance**; becoming *deposit* shows "Anchor required" or, if an entry was kept, that the entry applies again). The status line says what happened. `nothing_to_change`, `invalid_account_name`, `invalid_account_type` and `account_not_found` are mapped to sentences.

## Chart Data Preparation (Epic 13, US-13.5, Question 2 = A)

All in `lib/balanceChart.ts`, pure, working on the API's strings.

- **Rank**: `rankSeriesAccounts(series)` orders the plotted accounts by the **absolute value of their last non-null SGD value in the range**, largest first (an overdrawn account is not hidden), ties by name case-insensitively then id; an account with no value at all ranks last.
- **Lines**: `buildBalanceLines(series, theme)` returns the combined line first (ink colour, 3 px, label "Combined total"), then the top **7** accounts in rank order with `CATEGORICAL_PALETTE[0..6]` (2 px, label the account's name), then, when more than 7 accounts are plotted, **"Other accounts (N)"** in the grey `OTHER_COLOR` summing the remaining accounts. This is the project's existing rule (at most eight distinct colours; the rest fold into a grey "Other") applied to balances, which cannot reuse the existing bar/line bucketing because that treats a missing value as zero.
- **Values stay strings.** The "Other accounts" value at a date is the exact sum (BigInt cents) of its members' **non-null** values there, and `null` only when every member is null (consistent with the API, whose combined total also leaves an account out rather than zeroing it). `Number(...)` is applied only when the arrays are handed to Chart.js; the tooltip and the summary re-format from the strings.
- **Gaps** are `null` in the data and Chart.js is told not to span them.
- **Labels** (`labelForPoint`): daily points "18 Oct", with the year when the range crosses a year ("18 Oct 2025"); month-end points "Oct 2026"; a final range-end point that is not a month end is labelled with its day ("18 Oct 2026"). Tooltips title the full date. Chart.js's tick auto-skipping handles crowding (up to 1,500 daily points).
- **Summary** (`summarizeSeries`): the first and last points whose combined total is not null, the exact change between them, in one sentence; with none: "There is no combined balance in this range."
- **Granularity** is the response's resolved value ("day"/"month"), shown beside the chart; the owner's Auto/Daily/Month-end choice is what is sent. A refused range (`invalid_date_range`, `range_too_large`) shows its sentence and keeps the previous chart.

## Display Rules (Epic 13)

- **Money**: always the API's two-place string, grouped with commas by `formatAmount`; prose and tooltips put the currency code first ("SGD 12,345.67"), table cells show the number and put the currency in the header or beside a non-SGD native figure ("1,234.56 USD"). Negative amounts keep a minus sign and a red tone. A value that is not available is "—", never "0.00".
- **Dates**: "5 Oct 2026", month names written out in the helper (not the browser's locale), parsed from the text so the owner's time zone can never move a date.
- **Wording**: the approved terms are used — "anchor required", "anchor" explained once as "a balance you know to be real on a date" — and status is always in words as well as colour ("Anchor required", "Unavailable: no exchange rate", "approximate", "statement shows more"). "Worked from" says what each figure rests on (AR-55) in the owner's terms: "your entered balance of 5 Oct 2026" / "the statement closing balance of 31 Aug 2026".
- A figure is never shown without its date context: the heading states the date; the ingested-through line sits with every result.

## Error Mapping (Epic 13)

`balanceErrorMessage(error)` turns the API's stable codes (AR-64) into plain sentences; any other `ApiError` shows the server's message; a non-API failure shows "Couldn't reach the server." The Frontend keeps its one error path.

| Code | Sentence |
|---|---|
| `account_not_found` | That account no longer exists; the list has been refreshed. |
| `invalid_anchor_value` | Enter the balance as a number with at most two decimal places, for example 1,234.50. |
| `anchor_date_in_future` | The date can't be after today. |
| `anchor_date_out_of_range` | The date is too far back; dates before 1 Jan 2000 aren't supported. |
| `not_a_deposit_account` | Only savings and current accounts have a balance. Change this account's type first. |
| `nothing_to_change` | Nothing was changed. |
| `invalid_account_name` | The name must be between 1 and 255 characters. |
| `invalid_account_type` | Choose savings or current account, credit card, or other. |
| `merge_same_account` | Choose a different account to merge into. |
| `merge_currency_mismatch` | These accounts are in different currencies, so they can't be one account. |
| `merge_appear_together` | These two accounts are listed together on one statement, so they are different accounts. If they look alike, rename them instead. |
| `merge_anchor_choice_required` | Both accounts have a balance entered. Choose which one to keep. |
| `merge_anchor_choice_invalid` | Choose the balance of one of these two accounts. |
| `date_in_future` / `month_in_future` | That is after today. Choose today or an earlier date. |
| `date_or_month_required` | Choose a date or a month. |
| `invalid_date_range` | The start must be on or before the end, the end can't be after today, and dates before 2000 aren't supported. |
| `range_too_large` | That range has too many points. Choose a shorter range or month-end points. |
| a 422 (malformed date) | That isn't a valid date. |

## Responsive, Theme, and Accessibility Rules (Epic 13)

Every new element carries its dark-mode classes; the chart takes its chrome from the shared `getChartTheme` and adds only a light and a dark ink colour for the combined line. Tables scroll horizontally inside their container instead of overflowing the page, and the accounts section is a wrapping list that needs no second layout. The Dashboard's tab strip scrolls sideways rather than wrapping. Buttons and links keep a comfortable touch size. The outcome of an action is announced politely (`role="status"`), the lookup result region is `aria-busy` while loading, tables have captions, form fields have labels, and the dialogs use the app's existing modal (focus trapped, restored on close). The chart is `role="img"` with the summary sentence as its label, and the exact figures are also written under it, so nothing depends on hovering or on seeing colour.

## Out of Scope for This Unit (Epic 13)

Clicking a chart point to look that date up, balance forecasts, exporting balances, editing a transaction's account, and re-linking the unlinked transactions (AR-60: information only). The user guide is updated at release, as for earlier epics.
