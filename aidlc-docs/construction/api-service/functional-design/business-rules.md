# Business Rules — Unit 2: API Service

API-layer validation rules. These either surface a Unit 1 DB-layer rule as a clean error before the DB rejects it, or add a rule that has no DB-layer equivalent.

## AR-1: Authentication Required
Every route except `POST /auth/login` MUST reject requests without a valid, unexpired JWT with `401 Unauthorized`. **Traces to**: FR-9.1.

## AR-2: Inactive Category Not Selectable
A category correction or new-category-assignment request MUST be rejected with `400 Bad Request` if the target category has `active = false` — surfaces BR-6 as an API-layer check rather than relying on the DB (which has no constraint preventing an inactive category FK reference, by design, since historical transactions must keep referencing it). **Traces to**: US-5.2 edge case, BR-6.

## AR-3: Reserved Category Immutable
A rename or remove request targeting the `is_reserved = true` (`UNSURE`) category MUST be rejected with `400 Bad Request`. **Traces to**: BR-5, FR-5.1.

## AR-4: Category Name Uniqueness (Pre-Check)
An add or rename request MUST be rejected with `400 Bad Request` (not a raw 500 from a DB unique-constraint violation) if the target name already exists among any category, active or inactive. **Traces to**: BR-4.

## AR-5: Category Removal Blocked While In Use
A remove request MUST be rejected with `409 Conflict` and the count of referencing transactions if any `Transaction` still references the category (Question 4 = A — count only, no full transaction list in the error body). **Traces to**: US-5.2 edge case.

## AR-6: Single Active Ingestion Run
A trigger-ingestion request MUST be rejected with `409 Conflict` (including the existing run's id) if any `IngestionRun` already has `status IN ('queued', 'running')`. **Traces to**: BR-10.

## AR-7: Manual Correction Requires Whitelist Category
A category-correction request's target category MUST exist and be active (AR-2); an unrecognized category id MUST be rejected with `400 Bad Request`, never silently coerced to `UNSURE`. **Traces to**: FR-6.2, FR-6.3.

## AR-8: Pagination Bounds
`pageSize` MUST default to 50 and be capped at 200; requests exceeding the cap MUST be clamped (not rejected) to avoid breaking a client that doesn't realize the cap exists, per Question 3 = A. CSV export (US-3.6) is exempt from this cap but has its own safety maximum of 50,000 rows.

## AR-9: Currency Filter Validation
Dashboard/transaction currency filters MUST validate against ISO 4217 3-letter codes; an unrecognized currency code MUST be rejected with `400 Bad Request` rather than silently returning zero results.

## AR-10: Retroactive Job Created Only for Manual Corrections
A `RecategorizationJob` row is inserted if and only if a category correction succeeds and results in `category_source = 'manual'` — never for any other category-source transition (there is no other transition this unit ever performs; auto-categorization writes only ever come from Unit 3). **Traces to**: BR-11, FR-5.4.

## AR-11: Proposal Must Exist to Approve or Reject (added 2026-08-02 — Epic 6)
Approving or rejecting a `recategorization_proposals` row that doesn't exist MUST return `404 Not Found`. In a bulk request, a not-found ID is reported as a per-item failure — it MUST NOT abort the rest of the batch. **Traces to**: FR-RR-6, FR-RR-7, US-6.4.

## AR-12: Proposal Must Be Pending to Resolve (added 2026-08-02 — Epic 6)
Approving or rejecting a proposal whose `status` is not `pending` MUST be rejected (`409 Conflict`) rather than silently accepted or silently re-applied — this is BR-16 (Unit 1) enforced at the API layer, guarding against a proposal being resolved twice (e.g. two overlapping bulk requests, or the same proposal appearing in two selections). In a bulk request, this is a per-item failure, not a whole-batch abort (same as AR-11). **Traces to**: BR-16, FR-RR-7, FR-RR-8.

## AR-13: Approval Writes Through, Rejection Never Touches the Transaction (added 2026-08-02 — Epic 6)
Approving a proposal MUST set the candidate transaction's `category_id` to the proposal's `proposed_category_id` and `category_source` to `similarity` (not `manual` — same reasoning as WR-5/AR-10: the change is applied algorithmically via a human's *review* action, not a direct edit to that specific transaction's fields). Rejecting a proposal MUST NOT modify the candidate transaction at all — only the proposal's own `status`/`resolved_at`. **Traces to**: FR-RR-7, FR-RR-8, US-6.4, US-6.5.

## AR-14: No-Prior-Backup Is a Valid, Distinct Response (added 2026-08-08 — Epic 7)
`GET /backups/status` MUST NOT error when no `BackupRun` row exists yet (e.g. immediately after this feature is first deployed, before the first scheduled attempt) — it returns a response with `outcome = null`, a third state the Frontend distinguishes from both `success` and `failed`. This endpoint performs a read-only query only; it never writes a `BackupRun` row itself (that remains exclusively the Ingestion Worker Service's responsibility, per `component-dependency.md`'s no-direct-call rule). **Traces to**: FR-10, FR-11.

## AR-15: Due Soon / Overdue / Pending Review / Paid Status Is Computed at Read Time (added 2026-08-08 — Epic 8; refined during Code Generation, see audit.md)
A `RecurringPayment`'s status is computed fresh on every request — never stored — from today's date, the payment's `due_day`/`due_month`, and whether a match exists for the current cycle:
- `paid` — a match with status `approved` or `auto_applied` exists for the current cycle (money confirmed).
- `pending_review` — a match with status `pending` exists for the current cycle (something was found, awaiting the user's decision, per FR-6/FR-9's explicit inclusion of `pending` among the statuses that prevent `overdue`).
- `overdue` — the due date has passed with no match of *any* status (`pending`/`approved`/`auto_applied`) for the current cycle. Immediate, no grace period (FR-9).
- `due_soon` — no match yet, and the due date is upcoming within a lead window (FR-10).

Refined from a 3-state model to this 4-state one during Code Generation: FR-9's literal wording ("no matched transaction (pending, approved, or auto-applied)") already implied a pending match prevents `overdue`, but a 3-state model with no distinct `pending_review` value would have had to misrepresent that case as either `paid` (wrong — nothing is confirmed yet) or `overdue` (wrong — FR-9 explicitly excludes it).

**Exact algorithm** (also refined during Code Generation, once it became clear "nearest instance to today" — the Worker's matching rule, WR-17 — is the wrong rule for status display: it can jump straight to next month's instance and silently skip checking whether *last* month's bill was ever paid):
1. `current_instance` = the most recent due-date instance on or before today (a due-date pattern recurs indefinitely, so this always exists, never "not due yet").
2. Look up a match for `current_instance`'s cycle:
   - `pending` → `pending_review`
   - `approved`/`auto_applied` → this cycle is paid; compute `next_instance` (the following due-date instance). If `next_instance` falls within the due-soon lead window of today, report `due_soon` anyway (nudging toward the upcoming one) — otherwise `paid`.
   - no match → `current_instance < today` → `overdue`; `current_instance == today` → `due_soon` (FR-9's explicit one-day grace: not overdue until the day *after* the due date).

Deferred here from the Ingestion Worker's Functional Design — this is a read-time aggregate, matching how Dashboard/Insights already computes its aggregates on read rather than persisting derived state. **Traces to**: FR-9, FR-10.

## AR-16: Annual Payments Include a Monthly Set-Aside Figure (added 2026-08-08 — Epic 8)
The status response for an `annual` `RecurringPayment` MUST include `expected_amount / 12` alongside its due-date status. **Traces to**: FR-11.

## AR-17: A Match Must Exist and Be Pending to Approve or Reject (added 2026-08-08 — Epic 8)
Approving or rejecting a `RecurringPaymentMatch` that doesn't exist MUST return `404`; one that isn't currently `pending` MUST return `409` rather than being silently accepted or re-applied — same pattern as AR-11/AR-12 (Epic 6), enforcing BR-23. **Traces to**: BR-23, FR-6, FR-7, FR-8.

## AR-18: Approval Writes Through and Trusts the Payment; Rejection Has No Other Side Effect (added 2026-08-08 — Epic 8)
Approving a `pending` match marks that cycle Paid and, if the owning `RecurringPayment.is_trusted` is not already `true`, sets it to `true` (FR-7 — the first approval is what unlocks future tolerance-gated auto-apply). Rejecting a `pending` match changes only that match's own `status`/`resolved_at` — it MUST NOT touch the transaction or the payment's `is_trusted` flag (FR-8), matching AR-13's precedent from Epic 6. **Traces to**: FR-6, FR-7, FR-8.

## AR-19: Bulk Import Validates Each Row Independently (added 2026-08-08 — Epic 8)
A bulk-import request processes every row independently — a malformed row (missing a required field, an invalid frequency value, or a due-date combination BR-19/BR-20 would reject) is collected as a per-row error in the response rather than aborting the whole import; valid rows are still created. **Traces to**: FR-3, NFR-4.

## AR-20: Dismissing or Adding a Detection Suggestion Resolves It Permanently (added 2026-08-08 — Epic 8)
Dismissing a `new` `DetectionSuggestion` sets its status to `dismissed`; because `description_pattern` is unique (BR-22), no future scan will ever create a new row for that same pattern — dismissal is permanent by construction, not by extra application logic. Adding from a suggestion creates a new `RecurringPayment` pre-filled from the suggestion's fields (editable before saving) and sets the suggestion's status to `added`. Acting on a suggestion that is not currently `new` MUST return `409`, same reasoning as AR-17. **Traces to**: FR-12, FR-13.

## AR-21: Embedding Status Is Read-Only, DB-Sourced (added 2026-08-13 — Local Embedding-Based Semantic Similarity, Epic 9)
`TransactionDTO.embeddingStatus` is read directly from `Transaction.embedding_status` (Database `BR-24`) with no additional query logic or business rule beyond exposing the column — this component never calls the Vector Store Client or embedding endpoint (Ingestion Worker Service-only). **Traces to**: FR-7, US-9.1.

## AR-22: Recurring Payment Name Changes Reset Embedding Status (added 2026-08-13 — Epic 9)
Creating a `RecurringPayment` sets `embedding_status = pending` (matching the column's own default, stated here for completeness). Updating a `RecurringPayment` MUST reset `embedding_status` to `pending` if and only if the update changes `name` — any other field change (`expectedAmount`, `dueDay`, `dueMonth`, `categoryId`, etc.) MUST leave `embedding_status` untouched, since the text the Ingestion Worker's Embedding Manager embeds is the `name` field only (Database `BR-25`). This is the *only* place `RecurringPayment.embedding_status` is ever set to `pending` after creation — the Ingestion Worker Service is the only writer of `completed`, and never writes `pending` itself; without this reset, a rename would leave the vector store matching against stale text indefinitely. **Traces to**: FR-1, FR-6, FR-10, FR-11 (Database `BR-25`).

## AR-23: A Disagreement Must Exist and Be Pending to Resolve or Reject (added 2026-08-16 — Matching Precision Refinement)
Resolving or rejecting a `CategorizationDisagreement` (FR-MPR-10/11) requires it to exist (404 if not) and be `status = pending` (409 if not — same pattern as AR-12/AR-17). Same reasoning as `ProposalNotPendingError`/`MatchNotPendingError`: there's no DB constraint enforcing single-resolution, so this layer is what actually prevents a double-resolve. **Traces to**: FR-MPR-10, FR-MPR-11 (Database `BR-27`).

## AR-24: Resolution Category Must Be One of the Two Offered Candidates (added 2026-08-16 — Matching Precision Refinement)
A resolve request's `chosenCategoryId` MUST equal either the disagreement's `similarity_category_id` or its `llm_category_id` — any other value is rejected (400), surfaced at this layer rather than only relying on Database `BR-27` (an application-layer rule there too, not a standing SQL constraint). This is what "pick one of the two" (FR-MPR-10) actually means as an enforced API contract, not just a UI convention the frontend happens to follow. **Traces to**: FR-MPR-10, FR-MPR-11 (Database `BR-27`).

## AR-25: Resolving Writes Through With Source-Matching category_source; Rejection Never Touches the Transaction (added 2026-08-16 — Matching Precision Refinement)
Resolving a disagreement writes the chosen category to the transaction with `category_source` set to whichever origin the chosen candidate came from (`similarity` if `chosenCategoryId == similarity_category_id`, `llm` if it equals `llm_category_id`) — never `manual`, since the human picked between two system-computed suggestions rather than typing a category from scratch (mirrors AR-13's `category_source='similarity'` on proposal approval, generalized to two possible sources here). Rejecting leaves the transaction untouched (`category_source` stays `unsure`) and keeps no suppression record — same no-memory policy as AR-13/FR-RR-8: a future ingestion of a similarly-described transaction can surface a fresh disagreement independently. **Traces to**: FR-MPR-11.

## AR-26: Pending Count Sums Proposals and Disagreements (added 2026-08-16 — Matching Precision Refinement)
The existing pending-count endpoint (US-6.6's nav badge) now returns the sum of pending `RecategorizationProposal` rows and pending `CategorizationDisagreement` rows as one number — the badge has always read generically as "items needing review," not "proposals" specifically, so no separate badge/endpoint is introduced for disagreements. **Traces to**: FR-MPR-10.

## AR-27: No Bulk Actions for Disagreements (added 2026-08-16 — Matching Precision Refinement)
Unlike proposals, disagreements have no bulk resolve/reject endpoint — resolving one always means a specific, individual choice between two different categories, which has no sensible bulk default (Application Design Decision 2). Bulk reject would be defensible on its own, but is deliberately not added either, to keep the action set symmetric and avoid a resolve/reject asymmetry that would need its own explanation in the UI. **Traces to**: FR-MPR-10.
