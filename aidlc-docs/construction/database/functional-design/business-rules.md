# Business Rules — Unit 1: Database

Invariants and validation logic the data layer must enforce or support. Traced to requirements.md and stories.md.

## BR-1: Category Reference Integrity
Every `Transaction.category_id` MUST reference an existing `Category` row (active or inactive — soft-deleted categories remain valid FK targets for historical transactions). **Traces to**: FR-4.3, US-5.2 edge case.

## BR-2: Exactly One Flow Direction
Exactly one of `Transaction.out_flow` / `Transaction.in_flow` MUST be a non-null, positive value; the other MUST be null. A transaction cannot be simultaneously an inflow and outflow, nor neither. **Traces to**: FR-2.3, FR-4.1.

## BR-3: Statement Hash Uniqueness
`BankStatement.pdf_content_hash` MUST be unique across all rows. This is the enforcement point for duplicate-statement prevention. **Traces to**: FR-3.1, FR-3.2.

## BR-4: Category Name Uniqueness
`Category.name` MUST be unique across all rows (active and inactive) — prevents ambiguity if a removed category name is reused. **Traces to**: FR-4.3, Requirements Section 5.

## BR-5: UNSURE Category Is Reserved
Exactly one `Category` row has `is_reserved = true` and `name = 'UNSURE'`. This row MUST always have `active = true` and MUST NOT be deletable or renameable at the application layer (the schema marks it; enforcement of the deletion/rename block is an API Service concern, but the `is_reserved` flag is the data-layer signal it relies on). **Traces to**: FR-5.1, FR-5.2 (step 4), Requirements Section 5.

## BR-6: Inactive Categories Excluded From New Selection
A category with `active = false` MUST NOT be assignable to a transaction going forward (neither by auto-categorization nor manual correction), but MAY continue to be referenced by transactions that were assigned it before deactivation (BR-1). **Traces to**: US-5.2 edge case (Question 3 = B, soft delete).

## BR-7: FX Rate Cache Uniqueness
The combination of (`FxRateCache.from_currency`, `FxRateCache.to_currency`, `FxRateCache.rate_date`) MUST be unique — one cached rate per currency pair per date, supporting fetch-once/reuse caching. **Traces to**: FR-10.4.

## BR-8: Conversion Flag Consistency
- If `Transaction.conversion_unavailable = true`, then `Transaction.converted_amount_sgd` MUST be null and `Transaction.fx_rate_used_id` MUST be null.
- If `Transaction.conversion_is_approximate = true`, then `Transaction.fx_rate_used_id` MUST reference an `FxRateCache` row whose `rate_date` differs from `Transaction.transaction_date` (a fallback/nearest-prior-date rate, per FR-10.5).
- A transaction cannot have both `conversion_unavailable = true` and `conversion_is_approximate = true`.

**Traces to**: FR-10.5, US-3.7 edge cases, US-4.6.

## BR-9: Failed File Requires a Reason
Any `IngestionRunFile` with `outcome = 'failed'` MUST have a non-null `failure_reason`. **Traces to**: FR-2.5, US-1.5 edge case.

## BR-10: Single Active Ingestion Run
At most one `IngestionRun` may be in status `queued` or `running` at any given time (enforced via a partial unique constraint on status, or application-layer check backed by this invariant). A new trigger request while one is active MUST be rejected. **Traces to**: US-1.2 (implicit — one run must complete before another starts to keep progress reporting unambiguous).

## BR-11: Recategorization Jobs Only From Manual Corrections
`RecategorizationJob.source_transaction_id` MUST reference a `Transaction` whose `category_source = 'manual'` at the time the job is created (only manual corrections are precedent-worthy per FR-5.3/5.4 — auto-assigned categories, even if unedited, do not trigger this retroactive re-scan). **Traces to**: FR-5.4, US-3.4 edge case.

## BR-12: Skipped File Links to Existing Statement
An `IngestionRunFile` with `outcome = 'skipped_duplicate'` SHOULD reference the pre-existing `BankStatement` row it matched via `bank_statement_id`, so the UI can show "already processed as part of run X" rather than just "skipped". **Traces to**: US-1.4, US-1.5.

## BR-13: Monetary Precision
All monetary columns (`out_flow`, `in_flow`, `converted_amount_sgd`, `FxRateCache.rate` where applicable) use fixed-point decimal with 2 decimal places (Question 4 = A) — no floating-point storage, to avoid rounding drift across repeated aggregation. **Traces to**: NFR data-integrity expectations (implicit from FR-8 aggregate accuracy).

## BR-14: No Duplicate Pending Proposals (added 2026-08-02 — Epic 6)
For a given `(candidate_transaction_id, recategorization_job_id)` pair, at most one `RecategorizationProposal` row may exist with `status = 'pending'` at a time. **Traces to**: NFR-RR-2.

## BR-15: Proposal Candidate Excludes Its Own Source (added 2026-08-02 — Epic 6)
A `RecategorizationProposal.candidate_transaction_id` MUST NOT equal `RecategorizationJob.source_transaction_id` for the job it belongs to — a transaction cannot be proposed as a match for the very correction that triggered the search. **Traces to**: FR-RR-1, US-6.1 edge case.

## BR-16: Proposals Are Resolved Exactly Once (added 2026-08-02 — Epic 6)
A `RecategorizationProposal` may only transition out of `pending` once (to `approved` or `rejected` by a user action, or to `auto_applied` at creation time — never both created-as-pending-then-auto-applied). Approving or rejecting a proposal that is not currently `pending` MUST be rejected as an error, not silently accepted. **Traces to**: FR-RR-7, FR-RR-8, US-6.4 edge case (prevents double-processing under concurrent bulk actions).

## BR-17: One Backup Attempt Per Calendar Day (added 2026-08-08 — Epic 7)
`BackupRun.backup_date` MUST be unique across all rows — at most one attempt (success or failure) per calendar day. This single constraint backs both "don't run a duplicate backup the same day" (US-7.1 edge case) and "don't auto-retry a failed backup the same night" (FR-9, US-7.4 edge case): once a row exists for a given date, no further attempt is made until the next calendar day. **Traces to**: FR-1, FR-9.

## BR-18: Failure Category Requires Failed Outcome (added 2026-08-08 — Epic 7)
`BackupRun.failure_category` MUST be null when `outcome = 'success'`, and MUST be one of `drive_connectivity` | `other` when `outcome = 'failed'`. This is the data-layer signal the Backup Status Component relies on to choose which message to show (reconnect-Drive prompt vs. generic failure indicator). **Traces to**: FR-10, FR-11.

## BR-19: Annual Recurring Payment Requires a Due Month (added 2026-08-08 — Epic 8)
`RecurringPayment.due_month` MUST be non-null when `frequency = 'annual'`, and MUST be null when `frequency = 'monthly'`. **Traces to**: FR-1.

## BR-20: Due Day Range (added 2026-08-08 — Epic 8)
`RecurringPayment.due_day` MUST be between 1 and 31 inclusive. Short-month edge cases (e.g. a due day of 31 in a 30-day month) are an application-layer concern (Ingestion Worker's due-date window calculation), not a data-layer one. **Traces to**: FR-1.

## BR-21: At Most One Live Match Per Recurring Payment Per Cycle (added 2026-08-08 — Epic 8)
For a given `(recurring_payment_id, cycle_period)` pair, at most one `RecurringPaymentMatch` row may have `status IN ('pending', 'approved', 'auto_applied')` at a time — enforced via a raw-SQL partial unique index, same pattern as BR-10 (`ingestion_runs`) and BR-14 (`recategorization_proposals`). A `rejected` row does not count, so a different transaction can still be proposed for the same cycle later (FR-8 leaves the door open; nothing is permanently suppressed). **Traces to**: FR-5, FR-6, FR-8.

## BR-22: Detection Pattern Uniqueness (added 2026-08-08 — Epic 8)
`DetectionSuggestion.description_pattern` MUST be unique across all rows — the entire enforcement mechanism behind FR-13's "a dismissed suggestion never reappears": one row exists per pattern for the lifetime of the database, and its `status` transitions rather than a new row being inserted on every re-scan. **Traces to**: FR-12, FR-13.

## BR-23: Matches Resolve Exactly Once (added 2026-08-08 — Epic 8)
A `RecurringPaymentMatch` may only transition out of `pending` once (to `approved`/`rejected` by a user action, or created directly as `auto_applied` — never both). Approving or rejecting a match that is not currently `pending` MUST be rejected as an error, not silently accepted — same pattern as BR-16. Application-layer enforced (Unit 2). **Traces to**: FR-6, FR-7, FR-8.

## BR-24: Embedding Status Is One-Way, Two-State (added 2026-08-11 — Local Embedding-Based Semantic Similarity, Epic 9)
`Transaction.embedding_status` only ever transitions `pending` -> `completed`, exactly once, written by the Ingestion Worker's Embedding Manager Component after it successfully computes and persists the transaction's embedding to the Vector DB. There is no `failed` state: a transient failure (endpoint unavailable, per FR-10) simply leaves the row `pending` for a later poll cycle to retry — this keeps the retry logic uniform (every `pending` row is always eligible, no separate failure/backoff bookkeeping) and matches FR-10's framing of a failure as "no embedding yet," not a distinct error condition the user needs to see differently from "not processed yet." Every new `Transaction` row (whether newly-ingested or pre-existing at migration time, FR-11) starts `pending` by default — this single default is what makes forward processing and the one-time historical backfill the same mechanism (see `domain-entities.md`'s Transaction addendum). Application-layer enforced (Unit 3, Embedding Manager Component). **Traces to**: FR-6, FR-7, FR-10, FR-11, NFR-4.

## BR-25: RecurringPayment Embedding Status Resets on Rename (added 2026-08-12, retroactively during Ingestion Worker Service Functional Design — Local Embedding-Based Semantic Similarity, Epic 9)
`RecurringPayment.embedding_status` follows the same one-way `pending` -> `completed` transition as BR-24, written to `completed` by the Ingestion Worker's Embedding Manager Component — but unlike `Transaction`, this field has a second write path: the API Service's Recurring Payments Component MUST (re)set it to `pending` whenever a `RecurringPayment` row is created OR its `name` is updated (FR-1 CRUD). This is what keeps the vector store's `recurring_payment_names` collection from silently going stale after a rename — the resolved answer to the Ingestion Worker Service Functional Design's Question 1 (Option A) requires this reset to actually deliver on "one unified, always-eventually-consistent mechanism," since a rename with no reset would otherwise leave `matchNewTransaction`/`runDetectionScan` matching forever against the old name's embedding. A `RecurringPayment` update that does not change `name` (e.g. `expected_amount`, `due_day`, `category_id`) MUST NOT reset `embedding_status` — no re-embedding is needed since the text being embedded hasn't changed. Application-layer enforced (Unit 2's Recurring Payments Component for the `pending` write path, Unit 3's Embedding Manager Component for the `completed` write path). **Traces to**: FR-1, FR-6, FR-10, FR-11, NFR-4.

## BR-26: LLM Suggested Category Is Write-Once (added 2026-08-16 — Matching Precision Refinement)
`Transaction.llm_suggested_category_id` is written exactly once, at the same time the transaction row is first persisted during ingestion (FR-MPR-1) — either to a real category (the LLM's classification) or left `null` (the LLM abstained with `UNSURE`, or its endpoint was unreachable, FR-MPR-1/NFR-MPR-2). It is never updated afterward by any later event — not a manual correction, not a proposal approval, not a disagreement resolution (BR-27) — since its entire purpose is preserving a historical record of what the LLM independently believed at ingestion time, for the retroactive re-scan's score-boost logic (FR-MPR-7) to read back later. Unlike `category_id` (mutable, reflects the transaction's current, actual category), this field is immutable once set. Application-layer enforced (Unit 3, Categorization Engine Component). **Traces to**: FR-MPR-1, FR-MPR-7.

## BR-27: Disagreement Resolution Must Be One of the Two Offered Candidates (added 2026-08-16 — Matching Precision Refinement)
`CategorizationDisagreement.resolved_category_id`, when set, MUST equal either `similarity_category_id` or `llm_category_id` on that same row — never a third, unrelated category. This is what "pick one of the two" (FR-MPR-10/11) actually means at the data layer: the human is choosing between two system-computed suggestions, not entering a free choice (a free choice is still available via the plain `UNSURE`-category correction dropdown, unaffected by this feature). Same one-time-resolution shape as BR-16 (`RecategorizationProposal`) and BR-23 (`RecurringPaymentMatch`) — a `CategorizationDisagreement` may only transition out of `pending` once, to either `resolved` (with one of the two candidates written to both `resolved_category_id` and the transaction's own `category_id`) or `rejected` (transaction left `UNSURE`, no suppression record kept, same policy as BR-16/FR-RR-8). Application-layer enforced (Unit 2, Recategorization Review Component). **Traces to**: FR-MPR-9, FR-MPR-10, FR-MPR-11.
