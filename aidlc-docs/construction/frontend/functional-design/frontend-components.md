# Frontend Components — Unit 4: Frontend SPA

Framework-agnostic component hierarchy, state, interaction flows, validation, and API integration points. Consumes Unit 2's REST API exclusively (`api-service/functional-design/domain-entities.md` for DTO shapes, `api-service/code/api-layer-summary.md` for the actual endpoint list including `/drive/*`).

## Component Hierarchy

```
App
  AuthProvider                          (session state: token in sessionStorage per Question 1 = C)
  Router
    LoginPage                           (/login)
      LoginForm
    ProtectedLayout                     (redirects to /login if no valid session)
      NavBar                            (Addendum 2026-08-02: PendingReviewBadge, US-6.6)
      DashboardPage                     (/)
        DateRangeFilter                 (shared across the 3 tabs below)
        CategoryTrendsTab
        CashFlowTab
        BankBreakdownTab
      TransactionsPage                  (/transactions)
        TransactionFilterBar
        TransactionTable
          TransactionRow                (inline category correction, Question 3 = A)
        ExportCsvButton
      IngestionPage                     (/ingestion)
        TriggerRunButton
        ActiveRunProgress
        RunHistoryTable
          RunFileDrilldown
      SettingsPage                      (/settings)
        CategoryManagement
        DriveConnectionCard
      ReviewPage                        (/review — Addendum 2026-08-02, Epic 6)
        ProposalTable
          ProposalRow                   (per-row approve/reject, select checkbox)
        BulkActionBar                   (select-all, bulk approve, bulk reject)
```

## LoginPage / LoginForm

- **Props/State**: local form state `{username, password}`, `submitting` boolean, `error` string
- **Validation**: both fields required (non-empty) before enabling submit; no client-side password strength rules (this isn't registration)
- **Interaction flow**: submit -> `POST /auth/login` -> on success, store token in `sessionStorage`, set `AuthProvider` state, redirect to `/`; on 401, show "Invalid username or password" inline (never reveal which field was wrong, matching US-5.1 edge case)
- **API**: `POST /auth/login`

## AuthProvider

- **State**: `token: string | null`, `expiresAt: datetime | null`
- **Behavior**: on app load, reads token from `sessionStorage`; every authenticated API call includes `Authorization: Bearer <token>`; on any `401` response from any API call, clears the session and redirects to `/login` (handles both expiry and the sliding-expiry token refresh — see business-logic-model.md)
- **Logout**: clears `sessionStorage` and in-memory state, redirects to `/login` (client-side only, per Unit 2's stateless-JWT design — no server-side revocation call)

## DashboardPage / DateRangeFilter / *Tab components

- **Shared state** (lifted to `DashboardPage`): `dateFrom`, `dateTo`, `currency?` — changing any of these refetches all 3 tabs' data
- **CategoryTrendsTab**: chart of category totals per month; disclosure banner shown when `disclosure.approximateCount > 0` or `excludedCount > 0`; clicking a chart segment navigates to `/transactions?category=<name>&dateFrom=<segment month start>&dateTo=<segment month end>` (US-4.5 drill-down)
- **CashFlowTab**: income/expense/net chart per month; same disclosure pattern
- **BankBreakdownTab**: per-bank totals per month; same disclosure pattern
- **API**: `GET /dashboards/category-trends`, `GET /dashboards/cash-flow`, `GET /dashboards/bank-breakdown`

## TransactionsPage / TransactionFilterBar / TransactionTable / TransactionRow

- **Filter state**: `dateFrom, dateTo, bank, category, flowDirection, currency, textSearch, categorySource, groupBy, sortBy, sortDir, page, pageSize` — mirrors `TransactionFilter`/`TransactionListQuery` (Unit 2). Reflected in the URL query string so filtered views are shareable/bookmarkable and drill-down links (from Dashboard) work.
- **`categorySource=unsure` quick filter**: a single-click toggle/chip (US-3.5), not a raw dropdown value the user has to know to select
- **TransactionRow inline correction** (Question 3 = A): clicking the category cell swaps it for a `<select>` of active categories; on change, calls `PUT /transactions/{id}/category`; on success, updates the row in place and shows a brief toast noting the retroactive-recategorization job was queued (informational only, no need to poll its completion)
- **Validation**: the category `<select>` is populated only from currently-active categories (mirrors AR-2 — the UI shouldn't even offer an inactive category as a choice, though the API still enforces it)
- **Grouping**: a `groupBy` selector; when set, `TransactionTable` renders grouped section headers with subtotals (from `TransactionPage.groups`) above the flat row list
- **API**: `GET /transactions`, `PUT /transactions/{id}/category`
- **Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9, US-9.1)**: `TransactionRow` renders a small, quiet badge (a dot/icon with a `title` tooltip, not a banner) next to the description, reflecting `txn.embeddingStatus` (`'pending'` | `'completed'`, already present on every `TransactionDTO`). Purely presentational — no polling, no new API call, no new column (inline in the existing Description cell to avoid touching `GroupHeaderRow`'s fixed `colSpan`). Per FR-7, this is a processing-status indicator only ("has this transaction's embedding been computed"), not a claim about match quality or precedent found — deliberately styled to not compete for attention with anything actionable elsewhere on the page.

## ExportCsvButton

- **Behavior**: triggers a browser download from `GET /transactions/export.csv` using the *current* filter state (no pagination params). **Resolved in Code Generation** (2026-08-01): implemented as `fetch` + `Blob` + a programmatically-clicked temporary anchor, not a direct `<a href>` navigation — the export endpoint requires the same JWT as every other route (AR-1), and a plain browser-initiated navigation has no way to attach an `Authorization` header.

## IngestionPage / TriggerRunButton / ActiveRunProgress / RunHistoryTable / RunFileDrilldown

- **TriggerRunButton**: disabled while `ActiveRunProgress` shows a run in `queued`/`running` state; on click, `POST /ingestion/runs`; on `409` (AR-6), shows "A run is already in progress" and switches to showing that run's progress instead of erroring uselessly
- **ActiveRunProgress**: polls `GET /ingestion/runs/{id}` every 3 seconds while `status` is `queued` or `running`; stops polling once `completed`/`completed_with_failures`/`failed`; displays `filesFoundCount/filesProcessedCount/filesSkippedCount/filesFailedCount` as a live progress readout (US-1.2's "near-live" requirement)
- **RunHistoryTable**: paginated list from `GET /ingestion/runs`, most recent first
- **RunFileDrilldown**: expanding a run row calls `GET /ingestion/runs/{id}/files`, shows per-file outcome and `failureReason` when present (US-1.5)
- **API**: `POST /ingestion/runs`, `GET /ingestion/runs`, `GET /ingestion/runs/{id}`, `GET /ingestion/runs/{id}/files`

## SettingsPage / CategoryManagement / DriveConnectionCard

- **CategoryManagement**: list (`GET /categories`, shows `active`/`isReserved` flags visually), add (form: name, required, non-empty), rename (inline edit, same validation), remove (confirm dialog first since it's a state-changing action per the "explicit permission" pattern for irreversible-feeling actions; on `409` from AR-5, show "N transactions still use this category" and suggest filtering to it in Transactions first)
- **Reserved category** (`UNSURE`): rename/remove controls are disabled in the UI (not just relying on the API's `400` per AR-3) with a tooltip explaining why
- **DriveConnectionCard**: shows connected/not-connected state (`GET /drive/status`); "Connect Google Drive" button calls `GET /drive/connect` then does `window.location = authorizationUrl` (full-page navigation to Google, per the standard OAuth web-app pattern); on return, the app lands back on `/settings?driveConnected=true` (Unit 2's callback redirect target) and re-fetches `/drive/status` to confirm
- **API**: `GET/POST /categories`, `PUT/DELETE /categories/{id}`, `GET /drive/status`, `GET /drive/connect`

## SettingsPage: Application Settings Section (Addendum 2026-08-16 — Configurable Application Settings)

- **ApplicationSettingsSection**: a new, third section on the existing Settings page, below `CategoryManagement` (US-10.1) — a plain list from `GET /settings` (40 rows), grouped visually into "Standard" and "Advanced" sub-groups by each row's `classification` field (US-10.2); the "Advanced" sub-group has a heading-level warning banner, not a per-row tooltip, since the risk framing (US-10.2's "specific, not generic" requirement) is per-setting text shown when a row is actually being edited, not in the collapsed list view.
- **SettingRow**: shows `name`, current `value`, and (for Advanced rows) a short risk note sourced from a static frontend-side copy table keyed by setting name (matching each Advanced setting's specific consequence already documented in `business-rules.md` AR-28 / the original requirements doc's Advanced table — e.g. `embedding_base_url`'s "a wrong value here disables embedding matching with no error shown"). Clicking a row (or an "Edit" affordance on it) opens an inline edit form — a text input pre-filled with the current value, type/range hint text derived from the row's `type`/`min`/`max`/`allowedValues` fields (client-side hint only; the real enforcement is server-side, AR-28).
- **Save flow**: submitting the inline edit form does NOT call `PUT /settings/{name}` directly — it opens a `SettingConfirmDialog` (Radix `Dialog`, same primitive `CategoryRow`'s remove-confirmation already uses) summarizing "Change `{name}` from `{currentValue}` to `{newValue}`?" plus which service(s) will need restarting (from a client-side static owning-service lookup, same data source as the risk-note table) — per FR-CAS-10/US-8's confirmation-step requirement, distinct from `CategoryManagement`'s lower-friction inline-save. Confirming calls `PUT /settings/{name}`; a `400 invalid_setting_value` response is shown inline on the edit form (not the dialog, which has already closed) so the user can correct the value without losing their place; a `404 unknown_setting` should never happen from the UI's own controls (only reachable by a name not in the `GET /settings` response) and is treated as an unexpected-error toast, not a form-level message.
- **RestartGuidanceBanner**: shown after a successful save, summarizing the response's `restartGuidance` array — one line per target (`docker restart transactagent-worker` / `docker restart transactagent-api`), the command rendered in a `<code>` block (copy-to-clipboard, no execution — this app has no Docker-socket access, Resolved Decision 2). For a target with `workerBusy: true` (Ingestion-Worker-owned settings only — the field is simply absent, not `false`, for `api-service`-owned ones, matching the API's own `response_model_exclude_none`), the banner shows "Worker is currently processing — wait for it to finish before restarting" instead of the ready-to-run command, and polls `GET /settings/{name}/restart-guidance` (a light interval, looser than `ActiveRunProgress`'s 3s — this is advisory background status, not something the user is watching complete moment-to-moment) until `workerBusy` flips to `false`, at which point the command replaces the waiting message (US-10.3).
- **SettingHistoryList**: a collapsible section (collapsed by default, to avoid competing with the settings list itself for attention) showing `GET /settings/history`'s rows — setting name, previous → new value, and a relative timestamp, most recent first, no pagination (a plain scrollable list, matching `CategoryManagement`'s own un-paginated list precedent) (US-10.4).
- **API**: `GET /settings`, `GET /settings/{name}`, `PUT /settings/{name}`, `GET /settings/{name}/restart-guidance`, `GET /settings/history`

## NavBar / PendingReviewBadge (Addendum 2026-08-02 — Epic 6)

- **PendingReviewBadge**: a small count badge next to the "Review" nav link, visible only when `pendingCount > 0` (US-6.6). Polls `GET /recategorization/proposals/pending-count` on an interval — chosen deliberately looser than `ActiveRunProgress`'s 3s (that polls a run the user is actively watching finish; this polls a background number that's fine to be up to a minute stale) — see business-logic-model.md for the exact interval and reasoning.
- **API**: `GET /recategorization/proposals/pending-count`

## ReviewPage / ProposalTable / ProposalRow / BulkActionBar (Addendum 2026-08-02 — Epic 6)

- **ProposalTable**: paginated list from `GET /recategorization/proposals`, most recent first; each `ProposalRow` shows the candidate transaction (date, description, amount, current category), the proposed category, match score, and source bucket (`unsure`/`categorized` — surfaced as a small label so the user can tell "this was uncategorized" apart from "this already had a category" at a glance, since the latter deserves more scrutiny per FR-RR-4)
- **ProposalRow**: a checkbox (feeds `BulkActionBar`'s selection state) plus per-row Approve/Reject buttons — `POST /recategorization/proposals/{id}/approve` or `/reject`; on success, the row is removed from the list (React Query cache invalidation) and the nav badge count decrements
- **BulkActionBar**: a "select all" checkbox (selects every row on the *current page*, not across pages — consistent with `ExportCsvButton`'s existing "acts on what's visible/filtered" precedent rather than an unbounded "select everything ever" action) plus "Approve selected" / "Reject selected" buttons, calling `POST /recategorization/proposals/bulk-approve` / `bulk-reject`; disabled when the selection is empty
- **Bulk result handling**: the bulk endpoints return `{approvedIds/rejectedIds, failedIds}` (AR-11/AR-12 partial-failure shape) — rows in `*Ids` (succeeded) are removed from the list; rows in `failedIds` stay visible with an inline "couldn't process — it may have already been resolved" note, rather than silently disappearing or erroring the whole action (US-6.4's "select one or more or all" implies partial success is a first-class, expected outcome, not an edge case to hide)
- **Empty state**: "No proposals waiting for review" when the page has zero items
- **API**: `GET /recategorization/proposals`, `POST /recategorization/proposals/{id}/approve`, `POST /recategorization/proposals/{id}/reject`, `POST /recategorization/proposals/bulk-approve`, `POST /recategorization/proposals/bulk-reject`

## DisagreementTable / DisagreementRow (Addendum 2026-08-16 — Matching Precision Refinement)

- **DisagreementTable**: a second, separate table on the Review page (below `ProposalTable`, its own heading — same "visually separate section" convention `BackupStatusPanel` established, not merged into the proposals list since it's a genuinely different row shape), paginated from `GET /recategorization/disagreements`
- **DisagreementRow**: shows the candidate transaction (date, description, amount), the similarity-sourced candidate category, the LLM-sourced candidate category, and the similarity score; actions are "Use [similarity category name]", "Use [LLM category name]", and "Reject" — `POST /recategorization/disagreements/{id}/resolve` (body `{chosenCategoryId}`, one of the two candidates' ids) or `POST /recategorization/disagreements/{id}/reject`; on success, the row is removed and the nav badge count decrements (same combined count as proposals, AR-26)
- **No checkbox, no bulk actions** (Application Design Decision 2 / AR-27) — resolving is always an individual, specific choice between two different categories; `DisagreementRow` has no `BulkActionBar` equivalent
- **Empty state**: no separate message — the table section simply doesn't render when there are zero pending disagreements, same as `BackupStatusPanel` never hiding itself but `ProposalTable`'s own empty state already covers "nothing to review" messaging generally
- **API**: `GET /recategorization/disagreements`, `POST /recategorization/disagreements/{id}/resolve`, `POST /recategorization/disagreements/{id}/reject`

## BackupStatusPanel (Addendum 2026-08-08 — Epic 7)

- **BackupStatusPanel**: rendered on the Review page, visually separate (its own bordered section) from `ProposalTable` — per the requirements clarification that explicitly asked for this, not folded into the proposal review UI. Polls `GET /backups/status` on an interval (looser than `PendingReviewBadge`'s 30s — a nightly backup changes at most once a day, so this is an even less time-sensitive ambient indicator; see `business-logic-model.md` for the exact interval).
- **Three display states**, driven directly by `BackupStatusResponse.outcome` (AR-14):
  - `outcome === null` (no backup has run yet): a neutral "No backups yet" message
  - `outcome === 'success'`: last backup time and transaction count
  - `outcome === 'failed'`: `failureCategory === 'driveConnectivity'` shows a prompt to reconnect Google Drive (linking to the existing Settings page's connect flow); any other failure category shows a generic "Backup failed" indicator — both per FR-11's explicit dual-message requirement
- **API**: `GET /backups/status`

## DashboardPage: Recurring Payments Tab (Addendum 2026-08-08 — Epic 8)

- A 4th tab on the existing Dashboard page (FR-4) — not a separate nav page. Unlike the other 3 tabs, this one doesn't use the shared date-range filter (it's a live status view, not a historical time series).
- **Status summary**: 4 counts (due soon / overdue / pending review / new suggestions) shown at the top.
- **Payments list**: name, expected amount, frequency/due date, a status badge (`dueSoon`/`overdue`/`pendingReview`/`paid`, per AR-15), monthly set-aside for annual payments (AR-16), optional category. Add-one-at-a-time form (US-8.1) plus a bulk-import textarea for pasted rows (US-8.2), matching `SettingsPage`'s category-management form pattern.
- **Pending matches**: a compact table with per-row Approve/Reject (US-8.4), same interaction shape as `ReviewPage`'s `ProposalTable`.
- **Detection suggestions**: a compact list with per-row Add/Dismiss (US-8.6).
- **API**: `GET/POST /recurring-payments`, `PUT/DELETE /recurring-payments/{id}`, `POST /recurring-payments/bulk-import`, `GET /recurring-payments/matches`, `POST /recurring-payments/matches/{id}/approve`, `POST /recurring-payments/matches/{id}/reject`, `GET /recurring-payments/detection-suggestions`, `POST /recurring-payments/detection-suggestions/{id}/dismiss`, `POST /recurring-payments/detection-suggestions/{id}/add`, `GET /recurring-payments/status`

## NavBar: Recurring Payments Badge (Addendum 2026-08-08 — Epic 8)

- A badge on the **Dashboard** nav link (US-8.7), same visual pattern as `PendingReviewBadge` on Review — visible only when `overdueCount + pendingMatchCount + newSuggestionCount > 0` (`dueSoonCount` is informational, not counted — nothing has gone wrong yet).
- **API**: `GET /recurring-payments/status`

## NavBar: ActivityIndicator + ActivityPanel (Addendum 2026-08-18 — Background Process Visibility)

- **ActivityIndicator**: a new element in `NavBar.tsx`, separate from and visually distinct from `PendingReviewBadge`/`RecurringPaymentsBadge` per NFR-BPV-2 — a small pulsing/spinning dot, not an amber count-pill, since this represents "something is happening right now" rather than a backlog count. Polls `GET /background-activity/summary` on a fast interval (a few seconds, matching the Ingestion page's own active-run polling cadence per NFR-BPV-1 — looser than that page's per-run 3s poll is not required since this is ambient, but far tighter than the 30s/5min cadences of the two count badges).
- **Correction (2026-08-18, found during this same Functional Design pass)**: the original wording below said the idle state "renders nothing," copying the two count-badges' hide-at-zero convention too literally — but that would remove the only affordance for opening `ActivityPanel`'s history (US-11.3), which must stay reachable regardless of whether anything is currently running. Resolved: `ActivityIndicator` is always rendered as a clickable element (so history is always one click away); only its *visual weight* changes between states, per FR-BPV-4's actual wording ("hidden/**unobtrusive**", not "hidden entirely").
- **Two states, driven by `ActivitySummaryDTO.current`** (AR-35):
  - `current === null` (idle): renders as a small, muted/static dot — low visual weight, not competing for attention with the two count badges, but still present and clickable (FR-BPV-4).
  - `current !== null` (running): the same dot switches to pulsing/animated and gains a label from `current.jobType` (US-11.2) — "Ingestion run in progress" / "Recategorization scan in progress", never a generic "busy" label.
- **ActivityPanel**: a small popover/dropdown anchored to `ActivityIndicator` (click to open/close, same pattern as any existing dropdown in this UI — no new route/page), showing the current entry (if any) at the top and the `recent` list below it (job type + completion time, most recent first, US-11.3). Reuses the same `ActivitySummaryDTO` the indicator's own polling query already has (one `useQuery` call backs both the always-visible indicator and the on-demand panel content — no second network request when the panel opens).
- **Empty recent list**: shows a brief "No recent activity" message rather than an empty-looking blank area, per US-11.3's edge case.
- **Visible on every page** (US-11.1) — lives in `NavBar.tsx` itself, not per-page, same placement precedent as the two existing badges.
- **API**: `GET /background-activity/summary`

## Shared: Types, API Module, and Formatting Helpers (Addendum 2026-10-04 — Probable Duplicate Statement Detection, Epic 14)

- **Types** (mirroring the API design's DTOs; field names camelCase, enumerated values the API's snake_case strings): `StatementLabel`, `RemovalPreview`, `RemovalStatus`, `DuplicatePair`, `DuplicatePairPage`, `PendingPairCountResponse`, `RemovalRequest`, `ComparisonRow`, `ComparisonSide`, `DuplicateComparison`, `OverrideResponse`, `ScanStatus`. `RunFileOutcome` gains `"skipped_probable_duplicate"` (it is a closed union and would otherwise reject the new value); `RunFileDetail` gains `duplicateComparisonId: string | null` and `matchedStatement: StatementLabel | null`.
- **API module `api/duplicates.ts`** (one function per endpoint; paths fixed here so both units agree):
  - `GET /duplicates/pairs` (query `page`, `page_size`) -> `DuplicatePairPage`
  - `GET /duplicates/pairs/pending-count` -> `PendingPairCountResponse`
  - `GET /duplicates/comparisons/{comparisonId}` -> `DuplicateComparison`
  - `POST /duplicates/pairs/{pairId}/remove` (body `RemovalRequest`) -> `DuplicatePair`
  - `POST /duplicates/pairs/{pairId}/dismiss` -> `DuplicatePair`
  - `POST /duplicates/comparisons/{comparisonId}/override` -> `OverrideResponse`
  - `GET /duplicates/scan-status` -> `ScanStatus`
  - `POST /duplicates/recheck` -> `ScanStatus`
- **`formatStatementLabel(label)`**: "<file name> (<bank>, <period>)"; with no file name, "<bank> (<period>)"; with neither, "a statement (<period>)". **`formatPeriod(start, end)`**: "2 Jun to 30 Jun 2026" when both dates are in one year, "28 Dec 2025 to 3 Jan 2026" otherwise; month names are written out in the helper, not taken from the browser's locale, so the text is identical everywhere and in tests. Used by the Ingestion results, the panel, and the comparison page (A-PD-3).
- **`duplicateErrorMessage(error)`**: maps the API's stable error codes (`pair_not_pending`, `removal_not_offered`, `removal_already_requested`, `statement_missing`, `confirmation_out_of_date`, `not_a_skipped_file`) to plain sentences; any other error shows the server's message.

## NavBar / PendingDuplicatesBadge (Addendum 2026-10-04 — Epic 14)

- **PendingDuplicatesBadge**: a second count badge next to the "Review" link, beside the existing `PendingReviewBadge`, in a different colour (violet, with a dark-mode variant) so the two are told apart without reading; hidden when the count is 0 (US-14.5 "no badge when empty"); `aria-label` "N duplicate statements awaiting review"; `data-testid="pending-duplicates-badge"`. Polls `GET /duplicates/pairs/pending-count` every 30 seconds, mounted once at `NavBar`. Its count follows AR-40 (pending pairs with no removal in flight, information-only pairs included until dismissed).
- It does **not** change `PendingReviewBadge` or what its number means (NFR-PD-6).
- **API**: `GET /duplicates/pairs/pending-count`

## ReviewPage / DuplicateStatementsPanel / DuplicatePairRow / RemovalConfirmDialog (Addendum 2026-10-04 — Epic 14)

- **DuplicateStatementsPanel**: a bordered section (the backup panel's convention) on the Review page **below `DisagreementTable` and above the proposals table**, titled "Probable duplicate statements". Always rendered; its height depends on its state:
  - *Header line* (always): "Last checked <time>; <n> found" with a **Check again** button (`POST /duplicates/recheck`; afterwards "Re-check requested; the worker will look shortly").
  - *Detection off* (`scanStatus.detectionEnabled` false, nothing listed): "Duplicate detection is switched off." with a link to Settings.
  - *Nothing found* (detection on, nothing listed): "No probable duplicate statements."
  - *Groups*, each with its own heading and shown only when non-empty, from `GET /duplicates/pairs`: **Awaiting your decision** (pending pairs, information-only ones included), **Being removed** (removal queued, running, or cleaning up embeddings), **Removed in the last 24 hours** (done, or "removed; cleaning up search data failed, harmless").
  - Paginated (20 per page, Previous/Next) like the other review lists.
- **DuplicatePairRow**: shows the copy to **keep** and the copy proposed for **removal** (each: file name, bank, period, transaction count) and the manual corrections on each; a "View comparison" link to `/duplicates/<comparisonId>`; and:
  - *Removal offered*: **Remove duplicate…** (opens `RemovalConfirmDialog`) and **Not a duplicate — dismiss**.
  - *Information only* (`removalOffered` false): the note "These statements differ in size, so this is listed for information only." with **View comparison** and **Not a duplicate — dismiss** only; **no remove action** (Question 1 = C).
  - *Stale* (`stale` true): "One of these statements no longer exists." with dismiss only.
  - *Removal status* (when `removal` is present): queued, "Removing…", "Cleaning up…", "Removed" with the counts deleted, "Removed; cleaning up search data failed (harmless)", or "Removal failed: <reason>" with the actions available again so it can be retried.
  - A failed action shows its message inline on the row (`duplicateErrorMessage`).
- **RemovalConfirmDialog**: the app's existing dialog component (as the Settings page's confirmations), opened from a row. It states, from `pair.preview`: the transactions, statement sections, recategorization jobs and proposals, categorization disagreements and recurring-payment matches that will be **permanently deleted**; that the removed transactions' **embeddings are removed too**; how many transactions exist **only on this copy** and will be lost (`onlyOnRemovedCopy`); how many **manual corrections** on it will be lost (`correctionsLost`); and that the Drive file is left alone. Buttons **Cancel** and **Delete permanently** (disabled while the request is in flight). On confirm it sends `{removeStatementHash, acknowledgedCorrectionsLost}` from what the dialog showed. On an `confirmation_out_of_date`, `pair_not_pending`, `removal_not_offered`, or `statement_missing` answer the dialog closes, the list refreshes, and a message explains; nothing was deleted.
- After remove, dismiss, or "Check again": the pair list, the pending count (badge), and the scan status are refreshed together.
- **API**: `GET /duplicates/pairs`, `POST /duplicates/pairs/{id}/remove`, `POST /duplicates/pairs/{id}/dismiss`, `GET /duplicates/scan-status`, `POST /duplicates/recheck`

## ComparisonPage / ComparisonSidePanel / OverrideAction (Addendum 2026-10-04 — Epic 14)

- **ComparisonPage**: a route, `/duplicates/:comparisonId`, inside the same protected layout as every page, loading `GET /duplicates/comparisons/{id}`. A "Back" link returns to where the user came from (the Ingestion run results or the Review panel). It shows: a heading; a **state banner** (`skipped`: "Skipped as a probable duplicate"; `removed`: "Removed at your confirmation; the file is still in Google Drive"; `ingest_at_next_run`: "Will be ingested on the next ingestion run" with a link to the Ingestion page; `ingested_at_your_request`: "Ingested at your request"; `pair_pending`, `pair_dismissed`, `pair_superseded`: the pair's state in words); the stored **reason** (which already states a size difference prominently); the **headline figures** (both transaction counts, both periods, how many matched).
- **ComparisonSidePanel** (two of them): titled by role. For a skipped or removed file, `thisFileSide` makes the titles "This file" and "The statement it matches"; for a held pair, "Earlier ingested" and "Later ingested". Shows the statement label and a table of up to 10 rows (date, description, amount, currency), largest first (US-14.2). Each row carries a **text marker**, "Also on the other statement" or "Only on this one", plus a subtle tint, so meaning never depends on colour alone. A statement with 10 or fewer transactions shows all of them. Wide screens place the two panels side by side; narrow screens stack them; each table scrolls horizontally if needed.
- **OverrideAction**: shown only when `canOverride`. Button **Not a duplicate — ingest it** (`POST /duplicates/comparisons/{id}/override`). For `skipped` it is **one click**. For `removed` it first shows an inline warning ("This file will be ingested on the next run. The manual corrections that sat on this copy are not restored.") and needs a second click. On success the page re-reads the comparison, so the banner changes to "Will be ingested on the next ingestion run". A failure shows `duplicateErrorMessage`.
- For a held pair, the page also shows whether removal is offered and a link back to the Review panel; it offers no remove action itself (removal is confirmed only from the panel, where the preview is).
- **API**: `GET /duplicates/comparisons/{id}`, `POST /duplicates/comparisons/{id}/override`

## IngestionPage: RunFiles Outcome Cell (Addendum 2026-10-04 — Epic 14)

- In the per-file table of a run, a file whose outcome is `skipped_probable_duplicate` shows "Probable duplicate of <`formatStatementLabel(matchedStatement)`>" as a **link to `/duplicates/<duplicateComparisonId>`** (US-14.1/14.2). A file remembered from an earlier run appears the same way in a later run (US-14.4). Every other outcome renders as before; sorting by outcome still sorts on the stored value. Nothing else on the page changes.

## SettingsPage: Enumerated Settings as a Dropdown, and the New Category (Addendum 2026-10-04 — Epic 14)

- **Enumerated settings** (`type === "enum"` with `allowedValues`) are edited with a **dropdown** of those values instead of a free-text box, keeping the existing `data-testid` (`setting-input-<name>`); every other type keeps its text box. This corrects an earlier statement that a dropdown already existed. It also benefits the one existing enumerated setting (`low`, `medium`, `high`).
- **CATEGORY_ORDER** gains "Duplicate Statements", after "Ingestion". The three new settings (`duplicate_detection_enabled`, `duplicate_match_ratio`, `duplicate_min_transactions`) otherwise appear through the existing catalog-driven rendering, with the existing save confirmation and restart guidance (owning service: the Ingestion Worker). The switch's own description (from the API) says to enable it only after the accuracy check and that it takes effect when the worker restarts.

