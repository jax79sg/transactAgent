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
