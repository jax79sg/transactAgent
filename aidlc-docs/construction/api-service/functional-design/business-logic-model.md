# Business Logic Model — Unit 2: API Service

Technology-agnostic business logic for each of Unit 2's 5 components. Builds on Unit 1's domain model (`database/functional-design/`) — no new persisted entities are introduced here.

## Auth Component: Session Lifecycle

- **Login**: given `username` + `password`, look up `User` by username, verify `password_hash` (bcrypt/argon2-class hash comparison — exact library decided in NFR Requirements), and on success issue a signed JWT (Question 1 = A).
- **Token contents**: `sub` (user id), `iat`, `exp` (issued-at + 24h, Question 2 = A "sliding" — see below).
- **Sliding expiry**: any authenticated request that succeeds re-issues a fresh token with a renewed 24h `exp` (returned via a response header/cookie), so continuous use never logs the user out; 24h of *inactivity* is what actually expires the session.
- **Validation middleware**: every route except `POST /auth/login` requires a valid, non-expired JWT; invalid/expired/missing token -> `401 Unauthorized`.
- **Logout**: client-side token discard only (stateless JWT has no server-side revocation per Question 1 = A) — documented as a known, accepted limitation of the chosen approach for this single-user personal app.

## Transaction Management Component: Query/Filter/Group Logic

- **List/filter** (US-3.1, US-3.2): builds a SQL `WHERE` clause from optional filters (date range, bank, category, flow-direction, currency, text-search on `description` via `ILIKE`/full-text), applies offset/limit pagination (Question 3 = A: `page`, `pageSize`, default `pageSize=50`, max `pageSize=200`).
- **Group** (US-3.3): grouping is a `GROUP BY` at the SQL layer when only aggregates are needed (e.g., category subtotal view), or an application-layer bucketing pass over the already-filtered/paginated page when the UI needs both grouped headers and full row detail in one response — exact choice documented as an implementation note in NFR Design, since it affects whether pagination happens before or after grouping.
- **Manual correction workflow** (US-3.4, FR-5.4):
  1. Validate the new category is `active = true` (BR-6 enforced here, since the DB layer alone would allow selecting an inactive category)
  2. Update `Transaction.category_id`, set `category_source = 'manual'`
  3. Insert a new `RecategorizationJob` row with `status = 'queued'`, `source_transaction_id = <this transaction>` (BR-11 — only created here, only for manual corrections)
  4. Return the updated transaction to the caller immediately — the retroactive UNSURE re-scan happens asynchronously in Unit 3, per Application Design's `services.md`
- **CSV export** (US-3.6): re-runs the same filter/group query with no pagination limit (capped at a safety maximum, e.g., 50,000 rows, to avoid unbounded memory use) and streams/serializes to CSV with the same columns as the transaction table.
- **UNSURE filter shortcut** (US-3.5): a first-class filter value (`categorySource=unsure` or `category=UNSURE`) rather than requiring the client to know the reserved category's ID.
- **Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9, AR-21)**: `TransactionDTO` gains `embeddingStatus`, read directly from `Transaction.embedding_status` — no new query, just an added `SELECT` column on the existing list/get queries. Read-only; this component never writes it.

## Dashboard/Insights Component: Aggregation Logic

- **Category trends** (US-4.1, FR-8.1): `SELECT category, date_trunc('month', transaction_date), SUM(converted_amount_sgd) ... GROUP BY category, month` filtered to `out_flow IS NOT NULL` (spending only) and the requested date range.
- **Cash flow** (US-4.2, FR-8.2): `SUM(converted_amount_sgd) WHERE in_flow IS NOT NULL` vs `SUM(converted_amount_sgd) WHERE out_flow IS NOT NULL`, grouped by month; net = income - expenses.
- **Bank breakdown** (US-4.3, FR-8.3): `SUM(converted_amount_sgd) ... GROUP BY bank_name, month`.
- **All three** exclude transactions where `conversion_unavailable = true` from the SUM, but separately count them (`COUNT(*) WHERE conversion_unavailable = true`) to power the disclosure in US-4.6.
- **Approximate disclosure** (US-4.6): `COUNT(*) WHERE conversion_is_approximate = true` within the same filtered scope; both counts (approximate, excluded) are returned alongside every aggregate response, not just on request, so the UI can always show the disclosure affordance when non-zero.
- **Drill-down** (US-4.5): not a separate aggregation — the Frontend simply calls the Transaction Management list endpoint with a date+category filter derived from the clicked chart segment.

## Ingestion Trigger & Status Component: Trigger/Enqueue Logic

- **Trigger** (US-1.2): before inserting a new `IngestionRun` row with `status = 'queued'`, check for any existing row with `status IN ('queued', 'running')`. If found, return `409 Conflict` with the existing run's id (BR-10's application-layer surfacing — the DB constraint is the backstop, this check gives a clean error instead of a raw constraint-violation error).
- **Status polling** (US-1.2): simple read of the `IngestionRun` row (plus its `IngestionRunFile` children for per-file detail) by id; no special logic beyond a straightforward query — this is deliberately "dumb" per Application Design's decoupling (Unit 2 never talks to Unit 3 directly).
- **History** (US-1.5): paginated list of `IngestionRun` rows, most recent first; drill-down into one run's `IngestionRunFile` rows for per-file outcome/failure-reason detail (including `raw_extracted_text` availability, though the full text is only returned on an explicit detail request, not the summary list, to keep list responses small).

## Recategorization Review Component: Approve/Reject Logic (added 2026-08-02 — Epic 6)

- **List pending** (US-6.4): paginated list of `recategorization_proposals` rows with `status = 'pending'`, most recent first, joined to the candidate transaction (+ its current category) and the proposed category for display — deliberately "dumb", same reasoning as Ingestion Trigger & Status above: this component never talks to Unit 3 directly, it only reads what Unit 3 already wrote (AR-11 pattern, DB-only coordination).
- **Pending count** (US-6.6): a single `COUNT(*)` query scoped to `status = 'pending'`, exposed as its own lightweight endpoint separate from the list, since the nav badge shouldn't have to fetch a full page of proposal detail just to show a number.
- **Approve** (US-6.4, AR-11/AR-12/AR-13): find the proposal by id (404 if missing); reject (409) if not `pending`; otherwise write `proposed_category_id`/`category_source='similarity'` to the candidate transaction, set the proposal's `status='approved'` and `resolved_at=now()`.
- **Reject** (US-6.5, AR-11/AR-12/AR-13): find the proposal by id (404 if missing); reject (409) if not `pending`; otherwise set `status='rejected'`/`resolved_at=now()` only — the candidate transaction is never touched, and no suppression record is kept (FR-RR-8 — the same category may be proposed again later).
- **Bulk approve/reject** (US-6.4): applies the single-item logic per id in the request; a per-item 404/409 is collected into the response's `failedIds` rather than aborting the batch (AR-11/AR-12) — one bad id in a 20-item selection shouldn't block the other 19 from going through.
- **Addendum (2026-08-16, Matching Precision Refinement)**: Also owns review of `CategorizationDisagreement` rows (a distinct entity from `RecategorizationProposal` — Database, Key Design Resolution 1), reusing the same "dumb, DB-only, never calls Unit 3" shape:
  - **List pending disagreements** (FR-MPR-10): paginated list of `categorization_disagreements` rows with `status = 'pending'`, joined to the candidate transaction and both candidate categories (similarity-sourced, LLM-sourced).
  - **Resolve** (FR-MPR-10/11, AR-23/AR-24/AR-25): find by id (404 if missing); reject (409) if not `pending`; reject (400) if `chosenCategoryId` isn't one of the two offered candidates; otherwise write the chosen category to the transaction with `category_source` set to whichever origin it came from, set `status='resolved'`/`resolved_category_id`/`resolved_at=now()`.
  - **Reject** (AR-23/AR-25): find by id (404 if missing); reject (409) if not `pending`; otherwise set `status='rejected'`/`resolved_at=now()` only — the transaction is never touched.
  - **Pending count** (AR-26): folded into the existing `getPendingCount()` — the response is now `proposalPendingCount + disagreementPendingCount`, no new endpoint.
  - **No bulk variants** (AR-27) — see Application Design Decision 2 for why.

## Backup Status Component: Status Read Logic (added 2026-08-08 — Epic 7)

- **Get latest status** (US-7.4): a single query for the `BackupRun` row with the most recent `backup_date`, mapped to `BackupStatusResponse`. Deliberately "dumb," same reasoning as Ingestion Trigger & Status and Recategorization Review above — this component never talks to Unit 3 directly, it only reads what Unit 3's Backup Manager already wrote.
- **No-prior-backup case** (AR-14): if no `BackupRun` row exists at all, return `BackupStatusResponse` with every field `null` rather than a `404` — an empty result is a normal, expected state for a feature that hasn't reached its first scheduled run yet, not an error condition.
- **No write path**: unlike every other component in this service, Backup Status has no create/update/delete logic at all — `BackupRun` rows are written exclusively by the Ingestion Worker Service (component-dependency.md).

## Recurring Payments Component: Register, Review, and Status Logic (added 2026-08-08 — Epic 8)

- **CRUD** (US-8.1): standard create/update/delete against `RecurringPayment`; delete does not cascade-delete `RecurringPaymentMatch` history (a removed payment's past matches remain as historical record, just no longer produce new ones since the Worker only matches against currently-existing payments).
- **Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9, AR-22)**: create sets `embedding_status = pending` (the column's own default). Update resets it to `pending` only when the update changes `name` — every other field change leaves it untouched. This is the only write path that ever sets it `pending`; the Ingestion Worker Service's Embedding Manager is the only writer of `completed` (Database `BR-25`) — without this reset, a rename would leave the vector store matching against the payment's old name indefinitely.
- **Bulk import** (US-8.2, AR-19): each row is validated independently (required fields; `frequency` is `monthly` or `annual`; `dueMonth` present iff `annual`, matching BR-19; `dueDay` in 1–31, matching BR-20) — a row failing validation is collected into `failed` with a human-readable reason; valid rows are still created and returned in `created`.
- **Status computation** (US-8.3, AR-15/AR-16): for each `RecurringPayment`, compute the nearest due-date instance to today and its `cycle_period` using the *same algorithm* as the Worker's `cycle.py` (WR-17) — API Service and Ingestion Worker Service are separately deployable codebases with no shared library between them (per `component-dependency.md`), so this is necessarily a second implementation of the same date-math, not a shared import. Code Generation should keep the two implementations behavior-identical (same test cases mirrored on both sides) so the Dashboard's idea of "this cycle" always matches what the Worker actually matched against — flagged explicitly here so it isn't accidentally reinvented differently. Once the cycle is known, look up whether a live/resolved match exists for it. No match and today is past the due date → `overdue` (immediately, AR-15). No match and today is within the lead window before the due date → `due_soon`. A live match exists → `paid`. Annual payments additionally include `expected_amount / 12` as `monthlySetAside` (AR-16).
- **Review match** (US-8.4/8.5, AR-17/AR-18): find the match by id (404 if missing); reject (409) if not `pending`; approving sets `status='approved'`, `resolved_at=now()`, and — only if not already `true` — the owning payment's `is_trusted=true`; rejecting sets `status='rejected'`/`resolved_at=now()` only, touching nothing else.
- **Detection suggestion triage** (US-8.6, AR-20): dismiss sets `status='dismissed'` (permanent by construction, BR-22); add-from-suggestion creates a new `RecurringPayment` pre-filled from `descriptionPattern`/`suggestedAmount`/`suggestedCategoryId` (the caller can override any field before saving) and sets the suggestion's `status='added'`.
- **Status summary** (US-8.3/8.7): a single query returning the 4 counts backing the Dashboard section header and the nav badge — the badge itself only cares whether the sum of `overdueCount + pendingMatchCount + newSuggestionCount` is nonzero (matching `PendingReviewBadge`'s "hide entirely at zero" precedent); `dueSoonCount` is informational only, not counted toward the badge (nothing has gone wrong yet).
- **No write path for matching or detection itself**: this component only ever resolves what the Ingestion Worker's Recurring Payment Manager already proposed — deliberately "dumb," same reasoning as every other review-style component in this project (Ingestion Trigger & Status, Recategorization Review, Backup Status).

## Configuration Component: Category CRUD Logic

- **List** (US-5.2): returns all categories, `active` and inactive, with the `active` flag so the UI can visually distinguish and optionally hide inactive ones from selection dropdowns while still showing them in a "manage categories" admin view.
- **Add**: insert with `active=true, is_reserved=false`; rejects (`400`) if the name already exists (BR-4 surfaced cleanly rather than a raw DB error).
- **Rename**: updates `name`; rejects renaming a `is_reserved=true` row (BR-5, application-enforced).
- **Remove**: sets `active=false` (BR-6, soft delete) rather than a hard `DELETE`; before doing so, counts transactions referencing this category and rejects (`409`, Question 4 = A count-only) if count > 0; also rejects removing the `is_reserved=true` `UNSURE` row entirely (BR-5).

## Background Activity Component: Activity Summary Logic (added 2026-08-18 — Background Process Visibility)

- **Get activity summary** (US-11.1/11.2/11.3): two independent read-only queries, combined into one `ActivitySummaryDTO`:
  1. **Current**: `SELECT` the single `ingestion_runs`/`recategorization_jobs` row (across both tables) with `status = 'running'`, ordered by `started_at`/`created_at DESC LIMIT 1` (AR-35's defensive tie-break) — `null` if neither table has one.
  2. **Recent**: `SELECT` the 10 most-recently-completed rows across both tables (`completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 10`, AR-36) — a `UNION`-style combine-then-sort-then-limit, not two separate top-10s merged (so, e.g., 10 ingestion runs completed after the last recategorization job correctly crowds it out, rather than always reserving slots per type).
- **No write path**: same "deliberately dumb, read-only" shape as Backup Status and Recurring Payments' status summary — this component only ever reads what the Ingestion Worker's Ingestion Orchestrator / Categorization Engine already wrote via their existing `status`/`completed_at` transitions. No new writes anywhere in this feature.
- **No caching**: each call re-queries live, matching every other polling-backed endpoint in this codebase (`PendingReviewBadge`, `RecurringPaymentsBadge`) — NFR-BPV-1's fast cadence is achieved by polling frequently, not by adding a cache layer for a query this cheap (two small indexed lookups).

## Duplicate Review Component: Pairs, Comparisons, and Decisions (added 2026-10-04 — Probable Duplicate Statement Detection, Epic 14)

"Dumb" in the same sense as the recategorization review: it reads what the worker wrote and records the user's decisions; it never decides whether two statements match and never calls Unit 3. The router sits behind the login requirement (AR-1, AR-38).

- **List pairs** (AR-39, AR-41): the three groups, paginated; for each pair, labels from the stored comparison mapped to keep and remove by the stored `keep_hash`; the live manual-correction count on each copy; the preview (pending and removal offered only); the latest removal job as `removal`; `stale` when a statement is gone.
- **Pending count** (AR-40): one `COUNT(*)` of pending pairs with no active job.
- **Get comparison** (AR-45): the stored comparison with its rows by side, the derived state, `thisFileSide`, `canOverride`, and for a pair `pairId` and `removalOffered`.
- **Confirm removal** (AR-42):
```
pair = find(pairId)                                  -> 404
pair.status == pending                               -> 409 pair_not_pending
pair.removal_allowed                                 -> 409 removal_not_offered
no active job for the pair                           -> 409 removal_already_requested
both statements (by hash) exist                      -> 409 statement_missing
request.removeStatementHash == the non-keep hash     -> 409 confirmation_out_of_date
live manual corrections on that copy == request.acknowledgedCorrectionsLost   -> 409 confirmation_out_of_date
insert StatementRemovalJob(queued, pair, hash, corrections_acknowledged)       (unique-index conflict -> 409 removal_already_requested)
return the pair view (removal = the new job)
```
- **Dismiss** (AR-43): conditional update of a `pending` pair with no active job to `dismissed` with `decided_at`; otherwise the typed error.
- **Override** (AR-44): find the remembered file for the comparison in `probable_duplicate` or `confirmed_duplicate`; set `overridden` and `decided_at`; idempotent; a note for a removed copy.
- **Scan status and re-check** (AR-46): read the single scan-state row and the effective detection setting; the re-check sets its re-check time.

## Ingestion Trigger & Status Component: Run-File Detail Addendum (added 2026-10-04 — Epic 14)

Listing a run's files also returns, for a file whose outcome is `skipped_probable_duplicate`, its `duplicateComparisonId` and the structured `matchedStatement` label (AR-47). One extra join from the run file to its comparison (and to the remembered file for the matched side); a file with another outcome returns nulls. No change to run enqueueing, status, history, cancellation, or the log tail.

## Configuration Component: Detection Settings Addendum (added 2026-10-04 — Epic 14)

Three catalog entries and a lowercase-boolean display fix (AR-48). Everything else about Configurable Application Settings is unchanged: validation by the existing enumerated, decimal, and whole-number rules; the override-file write; the restart guidance (owning service: the Ingestion Worker); and the history row. The effective value of `duplicate_detection_enabled` is also read by the scan-status endpoint (AR-46).



---

# Epic 13 — Account Management and Balance Components (added 2026-10-18)

*Two new components of the API Service, each under its own router, reading and writing only the shared data store (AR-67). Both are new; neither changes an existing flow. Nothing is stored that can be computed (AR-66).*

## Account Management Component: Flows

**List accounts** (AR-51) — read the accounts, their keys, anchors, statement sections and a per-account transaction summary; order deposit, credit card, unknown, then by name; return each with `canHaveAnchor`.

**Rename / retype** (AR-52)
```
account = find(accountId)                        -> 404 account_not_found
request names name and/or type                   -> 400 nothing_to_change
name: trimmed, 1..255 characters                 -> 400 invalid_account_name
type: deposit | credit_card | unknown            -> 400 invalid_account_type
write name and/or type; a type change sets type_user_set (BR-34); the anchor row is left alone
return the account entry
```

**Set or replace the anchor** (AR-53)
```
account = find(accountId)                        -> 404 account_not_found
account.type == deposit                          -> 409 not_a_deposit_account
balance parses as a decimal, <= 2 places, in range  -> 400 invalid_anchor_value
asOfDate >= 2000-01-01                           -> 400 anchor_date_out_of_range
asOfDate <= today(reportingTimeZone)             -> 400 anchor_date_in_future
previous = current anchor (or none)
upsert the single anchor (balance, asOfDate)     -- one conditional write
return { anchor, previous }
```

**Merge** (AR-54, AR-65)
```
lock both accounts
survivor, absorbed exist                         -> 404 account_not_found
survivor != absorbed                             -> 400 merge_same_account
currencies equal                                 -> 409 merge_currency_mismatch
no statement has a section for both              -> 409 merge_appear_together
anchors: both present  -> keepAnchorFrom is one of the two          -> 409 merge_anchor_choice_required
         one present   -> keepAnchorFrom absent or that account      -> 400 merge_anchor_choice_invalid
         none          -> keepAnchorFrom absent                      -> 400 merge_anchor_choice_invalid
re-point the absorbed account's statement sections and keys to the survivor
keep the chosen anchor (delete the other, re-point if it was the absorbed account's)
reconcile the type (user-set choice wins) and the flag
delete the absorbed account
return the survivor's account entry
```

## Balance Component: Flows

**Reference point and balance** (AR-55, AR-56) — pure and shared by every read below.
```
knownBalances(account) = [anchor] + [printed closing balances with a date]   (same-date: anchor, else last recorded)
reference = the known balance nearest to D in days (tie: anchor, else earlier)
net       = inflows - outflows of the account's transactions strictly after the earlier of
            (reference.date, D) up to and including the later of the two
balance   = reference.value + net   if D >= reference.date
          = reference.value - net   if D <  reference.date
```

**Lookup** (AR-57, AR-58, AR-59, AR-60)
```
exactly one of date | month                      -> 400 date_or_month_required
D = date, or month -> last day (today for the current month)   -> 400 date_in_future / month_in_future
for each deposit account:
    no anchor                                    -> status anchor_required (excluded from the total)
    else balance in the account's currency (above)
         SGD account: as is
         other: nearest earlier cached rate on or before D -> SGD, rounded half-up to 2 places,
                approximate if the rate's date != D; none -> status fx_unavailable (excluded)
combined total = sum of the SGD balances of the ok accounts (rows add up exactly)
ingestedThrough = latest transaction date overall, and each account's own
unlinked notice = count, banks, dates, net per currency of transactions with no account link (or absent)
```

**Series** (AR-61)
```
from, to default: to = today, from = to minus 12 months; from <= to <= today; points <= 1,500   -> 400 invalid_date_range / range_too_large
granularity: auto -> day when (to - from) <= 92 days, else month; or the one asked for
dates: every day in [from, to]  |  every month end in [from, to] plus `to`
for each plotted account and date: exactly the lookup's balance for that date (same functions)
a date with no usable rate is a gap for that account; the combined value leaves that account out
accounts without an anchor: not plotted, listed once
```

**Discrepancies** (AR-62)
```
tolerance = balance_mismatch_tolerance (default 0.00)
for each deposit account with an anchor:
    statement differences: for each printed closing balance,
        computedFromAnchor = balanceFromKnown(anchor, closingDate, net)     -- anchor only
        difference = printed - computedFromAnchor ; listed when |difference| > tolerance
    period gaps: for each consecutive pair of printed closing balances (c1,p1) -> (c2,p2),
        gap = (p2 - p1) - net(transactions in (c1, c2]) ; listed when |gap| > tolerance
accounts without an anchor: nothing is checked, nothing is raised
```

## Configuration Component: Balances Settings Addendum (added 2026-10-18 — Epic 13)
Two catalog entries (AR-63), owned by the API Service; everything else about Configurable Application Settings is unchanged (validation rules, the override-file write, the restart guidance, the history row). The API reads `reporting_time_zone` for "today" (AR-57) and `balance_mismatch_tolerance` for AR-62 when it starts.
