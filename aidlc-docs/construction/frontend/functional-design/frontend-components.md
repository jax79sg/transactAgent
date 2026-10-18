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



---

# Epic 13 — Account Balance at a Point in Time (Addendum 2026-10-18)

*Functional Design for the Frontend SPA unit of Epic 13, answering the five questions in `construction/plans/frontend-account-balance-functional-design-plan.md` (Q1 = A, Q2 = A, Q3 = A, Q4 = A, Q5 = A). Stories US-13.2 to US-13.6. The API contract is `construction/api-service/functional-design/domain-entities.md` (Epic 13 section) **as corrected on 2026-10-18**: the series response names its range `start` and `end`, and the statement ids in the discrepancy DTOs may be null. Technology-agnostic where it can be; component names and `data-testid` values are fixed here so tests and Playwright agree.*

## Shared: Types, API Modules, and Helpers (Epic 13)

- **Types** in `api/types.ts`, mirroring the API's DTOs (camelCase fields; enumerated values the API's snake_case strings; money and balances are two-place **strings**, never numbers): `AccountType` (`"deposit" | "credit_card" | "unknown"`), `AnchorDTO`, `AccountDTO`, `AccountListResponse`, `AccountUpdateRequest`, `AnchorRequest`, `AnchorResponse`, `MergeRequest`; `AccountBalanceStatus` (`"ok" | "anchor_required" | "fx_unavailable"`), `BasisDTO`, `AccountBalanceDTO`, `ExcludedAccountDTO`, `UnlinkedNoticeDTO`, `BalancesResponse`; `BalanceGranularity` (`"auto" | "day" | "month"`), `SeriesAccountDTO`, `SeriesPointDTO`, `SeriesResponse` (with `start` and `end`), `StatementDifferenceDTO`, `PeriodGapDTO`, `AccountDiscrepancyDTO`, `DiscrepanciesResponse`. Statement ids are typed `string | null` where the API allows it.
- **`api/client.ts`**: the request-method type gains `"PATCH"` (the rename/retype call). Nothing else in the client changes; query keys are still camelCase and become snake_case on the wire, which leaves `date`, `month`, `from`, `to`, `granularity` unchanged.
- **`api/accounts.ts`** (one function per endpoint): `listAccounts()` -> `GET /accounts`; `updateAccount(id, {name?, type?})` -> `PATCH /accounts/{id}`; `setAnchor(id, {balance, asOfDate})` -> `PUT /accounts/{id}/anchor` (`AnchorResponse`); `mergeAccounts(survivorId, {absorbedAccountId, keepAnchorFrom?})` -> `POST /accounts/{id}/merge` (the survivor's `AccountDTO`).
- **`api/balances.ts`**: `getBalances({date} | {month})` -> `GET /balances`; `getBalanceSeries({from?, to?, granularity?})` -> `GET /balances/series` (with no `from`/`to` the API supplies the last 12 months ending today); `getDiscrepancies()` -> `GET /balances/discrepancies`.
- **`lib/money.ts`** (pure, no `Number`, no locale; the property-test targets): `formatAmount(text)` groups thousands in a decimal string ("12345.67" -> "12,345.67", "-1234.5" -> "-1,234.50"; a missing value is "—"); `formatMoney(text, currency)` -> "SGD 12,345.67"; `parseAmountInput(text)` accepts what a person types ("1234.5", "1,234.50", "-12.3", surrounding spaces; no currency symbol, no exponent) and returns the canonical two-place string or a reason ("not a number", "more than two decimal places"); `toCents(text)` / `fromCents(bigint)` and `addAmounts` / `subtractAmounts` for exact sums (BigInt cents). The Frontend never adds two amounts as floating-point numbers; `Number(...)` happens only at the chart boundary.
- **`lib/balances.ts`** (pure): `describeBasis(basis)` ("your entered balance of 5 Oct 2026" / "the statement closing balance of 31 Aug 2026"); `describeMonthLookup(response)`; `localToday()` (the browser's local calendar date, built from local year/month/day, **not** `toISOString()`); `dayBefore(iso)`; `mergeTypeOutcome(absorbed, survivor)` (mirrors the API's AR-54 type rule so the merge preview can state it); `nextAccountNeedingBalance(accounts, afterId)`; `balanceErrorMessage(error)` (below). Date text reuses the Epic 14 month-name table (`formatDay` is exported from `lib/duplicates.ts` for this and stays in one place).
- **`lib/balanceChart.ts`** (pure): `rankSeriesAccounts`, `buildBalanceLines`, `summarizeSeries`, `labelForPoint` (below).

## DashboardPage: Tabs, Date Filter, and the Balances Tab (Epic 13)

- The tab list gains a **fifth tab, "Balances"** (`data-testid="dashboard-tab-balances"`), after Recurring Payments. The Dashboard **still opens on Category Trends** (Q1 = A). The tab list scrolls sideways on a narrow screen and its triggers do not wrap, so five tabs fit a phone.
- `Tabs.Root` becomes **controlled** so the page knows the active tab. The page-level **From/To box is hidden while Balances is active** and shown again for the other four tabs, which are otherwise unchanged. (It filters the three older charts; the Balances tab has its own range.)
- **BalancesTab** (`data-testid="balances-tab"`) composes, top to bottom: `DiscrepancySummary`, `BalanceLookup` with its result (`IngestedThrough`, `UnlinkedNotice`, `BalancesTable`), `BalanceChart`, `AccountsSection`. It owns the lookup state; each part owns its own query.
- State that lives in `BalancesTab`: `lookup` (`{mode: "date", date}` or `{mode: "month", month}`), `autoLookup` (true until the user changes the lookup), and `serverToday` (the API's `today`, learned from the first successful lookup). Chart range and granularity live in `BalanceChart`. Leaving the tab discards them (the queries stay cached, so coming back is instant); no URL state.
- **API**: `GET /balances`, `GET /balances/series`, `GET /balances/discrepancies`, `GET /accounts` (reads); the writes are in the dialogs below.

## BalanceLookup (Epic 13, US-13.4)

- A two-way switch **Date | Month** (`lookup-mode-date`, `lookup-mode-month`). **Date**: a date input (`lookup-date-input`) with `min` 2000-01-01 and `max` the API's `today` (the browser's date until the first answer). **Month**: a month select and a year select (`lookup-month-select`, `lookup-year-select`), two plain selects because the browser's own month input does not exist in every browser; months after the current one are disabled. A **Today** button (`lookup-today-button`) sets the date to the API's `today`.
- Changing either control runs a new lookup; the previous result stays on screen, dimmed (`aria-busy`), until the new one arrives, so the screen does not flash empty.
- **Heading** (`lookup-heading`, from the response, never from the browser): date mode "Balances at the end of 18 Oct 2026"; month mode for a past month "Balances at the end of September 2026 (30 Sep 2026)"; the current month "Balances for October 2026 so far (to 18 Oct 2026, today)". A note under it: "Each figure is the balance at the end of that day, after that day's transactions."
- **Errors**: a 4xx answer shows its plain sentence (`balanceErrorMessage`) in `balances-error` with the controls still usable; a failure to load shows "Couldn't load balances" with a **Try again** button (`balances-retry`). The first lookup's special case is in the business logic model.

## IngestedThrough and UnlinkedNotice (Epic 13, FR-AB-14, Question 6 = A)

- **IngestedThrough** (`ingested-through`), shown on **every** result: "Transactions are ingested through 30 Sep 2026." When the looked-up date is after that date the line turns amber and adds "This date is later, so the figures don't include any activity after it." with a button **Show 30 Sep 2026** (`ingested-through-jump`) that moves the lookup to that date. With no transactions at all: "No transactions have been ingested yet."
- **UnlinkedNotice** (`unlinked-notice`), shown only when the response carries one: "99 transactions from GXS Bank, dated 1 Jul 2026 to 31 Jul 2026 (net SGD 18.65), belong to no account, so they are left out of every balance." Several banks are listed with commas; several currencies as "net SGD 18.65 and USD -2.00" (currencies are never added together). Information only: no button.

## BalancesTable (Epic 13, US-13.4)

- A real table (numbers align), scrolling horizontally inside its container on a narrow screen, with a visually hidden caption. Columns: **Account** (name; bank and identifier beneath), **Balance** (the account's own currency, shown only for a non-SGD account, as "1,234.56 USD"), **SGD**, **Worked from** (`describeBasis`), **Last transaction** (the account's own latest date, so a stale account stands out). One row per `AccountBalanceDTO` (`balance-row-<accountId>`), in the API's order.
- **Row states, always in words as well as colour**: `ok` shows the figures (`balance-native-<id>`, `balance-sgd-<id>`, `balance-basis-<id>`); an approximate SGD figure is prefixed "≈" and the row says "approximate: exchange rate of 14 Oct 2026" (`fxRateDate`); `anchor_required` shows **Anchor required** (`balance-status-<id>`) and a **Set balance** button (`set-balance-<id>`) that opens the BalanceDialog for that account; `fx_unavailable` shows **Unavailable: no exchange rate** and no figures. A negative balance shows a minus sign and a red tone, never colour alone.
- **Footer** (`combined-total`): "Combined total (N accounts): SGD 12,345.67", the sum as the API computed it. Beneath it **`combined-exclusions`** states every excluded account and why ("Not included: GXS Bank cket (anchor required), Trust Bank (no exchange rate)"); when the total is null: "No account has a balance yet. Enter one for each account to see a total." When `hasApproximate`, a line explains "≈ marks a figure converted at the nearest earlier exchange rate we have."
- A short explainer sits above the table until at least one balance exists: "An anchor is a balance you know to be real on a date, such as one from your banking app. The app works out every other date from it."
- **Empty state** (`balances-empty-state`): no deposit accounts: "No savings or current accounts yet. They appear here once statements have been ingested. Credit cards are never part of balances."

## BalanceChart (Epic 13, US-13.5)

- **Controls**: **From** and **To** date inputs (`series-from`, `series-to`; prefilled from the response's `start` and `end`, `max` the API's `today`), a three-way **Points** choice **Automatic | Daily | Month-end** (`series-granularity-auto`, `-day`, `-month`; Automatic by default), and **Last 12 months** (`series-reset`) which clears the dates so the API's default applies. The chart opens on the last 12 months (Q2 = A of the API unit).
- **What is drawn (Q2 = A)**: the **combined total** as a thick line in the theme's ink colour (not a palette colour), plus the **7 accounts with the largest balance** each in its own palette colour, plus, when there are more than 7 accounts, one grey **"Other accounts (N)"** line summing the rest. Clicking a name in the legend hides or shows that line (Chart.js's built-in behaviour). Values are plotted from the API's strings; a `null` is a **gap** (`spanGaps` off), never a zero and never joined across. Markers show only when a line has 40 or fewer points; all show on hover. Axis labels and tooltips are formatted by `formatAmount`/`formatMoney`; the tooltip lists every visible line at that date.
- **Beneath the chart**: the resolved points ("Showing every day" / "Showing month-end points", from the response's `granularity`); `series-summary` ("Combined balance went from SGD 10,000.00 on 18 Oct 2025 to SGD 12,345.67 on 18 Oct 2026 (+SGD 2,345.67).", the exact figures the chart can only show on hover); `series-not-plotted` ("Not plotted: GXS Bank cket (anchor required)", from `missingAccounts`); and, when any gap exists, "A break in a line means no exchange rate was available for that date."
- The chart container has `role="img"` and an `aria-label` that repeats the summary. Chart colours and chrome come from `getChartTheme(theme)`, so dark mode follows the existing shared theming; the ink colour has a light and a dark value.
- **Empty states**: no account has an anchor: "Enter a balance for at least one account to see the chart." (the not-plotted line still names them); a range with no points is prevented by the API's rules and is shown as the API's sentence if it is refused.
- **API**: `GET /balances/series`.

## DiscrepancyPanel (Epic 13, US-13.6, Question 3 = A)

- **DiscrepancySummary** (`discrepancy-summary`), at the very top of the Balances tab and **nowhere else**: with findings, "N accounts have differences with their statements." and a **Show details** / **Hide details** button (`discrepancy-toggle`, `aria-expanded`); with accounts checked and no findings, a quiet "Your statements agree with your balances (N accounts checked)."; with nothing checked (no anchor yet) it renders nothing. If its own query fails it shows "Couldn't check statement differences" with a retry link and the rest of the tab is unaffected. It never blocks or changes a figure.
- **DiscrepancyDetails** (`discrepancy-details`), opened by the button: one block per account (`discrepancy-account-<accountId>`, "<name> (<currency>): <statementsChecked> statements and <periodsChecked> statement-to-statement intervals checked") with two tables, each scrolling horizontally on a narrow screen:
  - **Statements that differ from your entered balance** (`statement-difference-row-<statementId or date>`): statement closing date, the balance the statement prints, the balance the app works out from your entered balance, and the difference (printed minus computed, signed, with the words "statement shows more" / "statement shows less" so the sign needs no decoding). Explanation: "A wrong entered balance or missing transactions before this date. Correct your entered balance and these disappear."
  - **Intervals where transactions don't explain the change** (`period-gap-row-<fromId or date>-<toId or date>`): from date, to date, the change the statements print, the net of the transactions between, and the gap. Explanation: "Transactions are probably missing or dated wrongly in this interval. This does not depend on your entered balance and stays until the transactions are fixed."
  - The statement is named by its closing date (the API returns no file name), e.g. "statement closing 30 Sep 2026".
- A footer states the tolerance ("Differences larger than 0.00 are listed; change this in Settings under Balances", with a link) and that only accounts with an entered balance are checked.
- **API**: `GET /balances/discrepancies`.

## AccountsSection (Epic 13, US-13.2 and US-13.3, Question 4 = A)

- `accounts-section` at the bottom of the Balances tab, titled "Accounts". A **list**, not a table, so it needs no second layout on a phone: one item per account (`account-row-<id>`) with a name line (name, and the identifier as printed), a detail line (bank; type in words, with "(set by you)" when `typeSetByUser`; currency), a figures line (the entered balance and its date, or "No balance entered", or "Not in balances" for a non-deposit account; statements, transactions, printed closing balances, latest transaction), and an actions line that wraps. Same-named accounts are told apart by identifier and the counts. Grouped under "Savings and current accounts", "Credit cards", "Other (type unknown)", in the API's order.
- **Actions** on every row: **Rename** (`account-rename-<id>`), **Change type** (`account-change-type-<id>`), **Merge into…** (`account-merge-<id>`, "this account is absorbed into the one you pick"); on a row with `canHaveAnchor`: **Set balance** or **Replace balance** (`account-set-balance-<id>`). A non-deposit account is offered no balance action. All disabled while a write is in flight.
- **Status line** (`account-status-message`, `role="status"`, polite): the outcome of the last action, until the next one ("Saved SGD 1,500.00 for 18 Oct 2026." / "Replaced SGD 1,234.00 (5 Oct 2026) with SGD 1,500.00 (18 Oct 2026)." / "Renamed to …" / "“A” is now a credit card and no longer in balances." / "Merged “A” into “B”.").
- Every write ends by refreshing **everything** that can show an account (`["accounts"]` and `["balances"]`), so a rename or a new balance appears in the lookup, the chart and the warnings at once.
- Loading and error states follow the page's own ("Loading accounts…", "Couldn't load accounts" with Try again). No accounts at all: "No accounts yet. They are created when statements are ingested."
- **API**: `GET /accounts`.

## BalanceDialog (Epic 13, US-13.3)

- The app's existing modal dialog (`Dialog` from Radix, as `RemovalConfirmDialog`), opened from a "Set balance" prompt or an account row, for one deposit account (`balance-dialog`). Title "Set the balance of <name>" / "Replace the balance of <name>".
- **Fields**: **Balance** (`balance-input`, a text field with decimal keyboard on a phone) and **Balance on** (`balance-date-input`, a date input, `max` the API's `today`). Beside them, in words: "In <currency>. Enter the balance at the **end of that day**, after that day's transactions." and "Use a figure from your banking app or a statement." The date starts at the date of the last balance entered in this visit (so a run of accounts for one day needs no retyping), else the API's `today`, else the browser's date.
- **Replacing**: above the fields, `balance-previous` shows the current entry ("Currently SGD 1,234.00 on 5 Oct 2026, entered 7 Oct 2026") and the button reads **Replace balance**; for a new entry **Save balance**. Both send the same request.
- **Validation before sending** (`parseAmountInput`, a date present and not after the API's `today`): a message beside the field (`balance-error`) and nothing is sent. The API remains the authority; its refusals show in the same place as plain sentences.
- **Save and next account** (`balance-save-next`), offered when another deposit account still has no balance: saves, then opens the dialog for the next one with the date carried over and the balance empty. **Cancel** closes without saving. On success the dialog closes (or moves on) and the status line is set.
- **API**: `PUT /accounts/{id}/anchor`.

## RenameDialog and ChangeTypeDialog (Epic 13, US-13.2)

- **RenameDialog** (`rename-dialog`): one text field (`rename-input`) prefilled with the name, a count "n/255"; **Save** (`rename-save`) is disabled while the trimmed name is empty, unchanged, or over 255. Names need not be unique; the dialog says nothing about uniqueness. **API**: `PATCH /accounts/{id}` with `{name}`.
- **ChangeTypeDialog** (`type-dialog`): three radio options with their consequences in words (`type-option-deposit`, `type-option-credit_card`, `type-option-unknown`): "Savings or current account: included in balances"; "Credit card: never part of balances"; "Other / not sure: left out of balances until you decide". The current type is preselected; **Save** (`type-save`) is disabled while unchanged. Extra text: leaving *deposit* — "It leaves balances, totals and charts straight away. A balance you entered is kept in case you change it back."; becoming *deposit* — "It will show Anchor required until you enter a balance" (or, with a kept entry, "Your entered balance of … applies again"); and always "Changing the type marks it as your choice, so later statements won't overwrite it." **API**: `PATCH /accounts/{id}` with `{type}`.

## MergeDialog (Epic 13, US-13.2)

- Opened by **Merge into…** on the account that will be absorbed (`merge-dialog`). Title "Merge “<A>” into another account".
- **Choose the account to keep** (`merge-target-select`): the other accounts **with the same currency**, each labelled with name, bank, identifier, type and statement count so same-named accounts can be told apart. With none: "There is no other <currency> account to merge into." Merging a deposit account into a credit card, or the reverse, is allowed (the API reconciles the type) and the preview says what happens.
- **Preview** (`merge-preview`), as soon as a target is chosen, in words and built from the two list entries: "All <n> statements and <m> transactions of “A” will count under “B”."; "“A” disappears from the list; “B” keeps its name."; "Later statements that match “A” will be filed under “B”."; the type outcome from `mergeTypeOutcome` only when the type changes ("“B” becomes a credit card because you set that type on “A”."); and "This can't be undone."
- **Balances**: if **both** have an entered balance, a required choice of two radios (`merge-keep-<accountId>`) showing each balance and date — no default, so neither is dropped silently; if only one has, "The balance entered for “X” (…) will be kept."; if neither, nothing. **Merge** (`merge-confirm`) stays disabled until a target is chosen and, where required, a balance kept; **Cancel** closes. It sends `{absorbedAccountId, keepAnchorFrom?}` to the **target's** path.
- **Refusals stay in the dialog** (`merge-error`) as plain sentences, nothing having changed: different currencies; "these two are listed together on one statement, so they are different accounts; if they look alike, rename them"; a balance choice missing or invalid; an account gone (the dialog closes and the list refreshes).
- **API**: `POST /accounts/{id}/merge`.

## SettingsPage: the Balances Category (Epic 13)

- `CATEGORY_ORDER` gains **"Balances"**, after "Duplicate Statements" and before "API & Access". `reporting_time_zone` and `balance_mismatch_tolerance` otherwise appear through the existing catalog-driven rendering, with the existing save confirmation and the API-restart guidance (owning service: the API Service). No new screen, no new component.

## NavBar (Epic 13)

- **Unchanged** (Question 5 = A): no badge for balances. The "anchor required" prompts in the Balances tab are the reminder.
