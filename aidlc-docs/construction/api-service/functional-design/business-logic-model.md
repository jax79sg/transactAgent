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

## Configuration Component: Category CRUD Logic

- **List** (US-5.2): returns all categories, `active` and inactive, with the `active` flag so the UI can visually distinguish and optionally hide inactive ones from selection dropdowns while still showing them in a "manage categories" admin view.
- **Add**: insert with `active=true, is_reserved=false`; rejects (`400`) if the name already exists (BR-4 surfaced cleanly rather than a raw DB error).
- **Rename**: updates `name`; rejects renaming a `is_reserved=true` row (BR-5, application-enforced).
- **Remove**: sets `active=false` (BR-6, soft delete) rather than a hard `DELETE`; before doing so, counts transactions referencing this category and rejects (`409`, Question 4 = A count-only) if count > 0; also rejects removing the `is_reserved=true` `UNSURE` row entirely (BR-5).
