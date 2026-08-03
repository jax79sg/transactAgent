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
