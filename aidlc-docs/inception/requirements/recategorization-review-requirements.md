# Requirements: Recategorization Review Panel

## Intent Analysis

- **User request**: "can i check. when the user change the category for a particular transaction, the the category for the other identical transaction gets changed as well? if worried of unsure, this can be a task for user to validate under a new task panel. user can choose to select one or more or all of the transactions to approve the auto update" — followed by explicit confirmation to run this "properly as a change" through Requirements Analysis, and answers to `recategorization-review-questions.md`.
- **Request type**: Enhancement to existing behavior (FR-5.4's automatic `UNSURE` sweep) + New Feature (a review/approval panel and a broadened, on-demand similarity search that don't exist today).
- **Scope estimate**: Multiple components — `database` (new entity), `ingestion-worker` (categorization pipeline behavior change), `api-service` (new endpoints), `frontend` (new page).
- **Complexity estimate**: Moderate — well-bounded, single-user, no new external integrations, but changes a currently-silent automatic-write behavior into a gated one and adds a second confidence tier to the existing similarity matcher.

## Current Behavior (baseline, confirmed against live code — see audit.md)

- `PUT /transactions/{id}/category` updates the corrected transaction immediately and unconditionally enqueues a `recategorization_jobs` row.
- `ingestion-worker` re-scans **only** transactions with `category_source = UNSURE` for similarity against the correction, using a single existing threshold (`settings.similarity_threshold`, in `categorization/similarity.py`). Matches are written directly to `transactions`, with `category_source` set to `SIMILARITY` — no review, no notification.
- Already-categorized transactions (from a prior similarity match, the LLM, or a manual edit) are never touched by this sweep.
- Nothing in the codebase — database, api-service, ingestion-worker, or frontend — has a "pending", "proposed", or "approve" concept. The frontend receives but discards the `recategorization_job_id`.

## Resolved Decisions (from clarifying questions)

| # | Decision | Answer |
|---|---|---|
| 1 | Scope | **Broadened** — a manual correction searches both the `UNSURE` backlog (today's behavior) and already-categorized transactions (similarity/LLM/manual-sourced) for matches, and surfaces both in the same review flow. |
| 2 | Timing | **Hybrid** — very-high-confidence matches auto-apply immediately, as today; everything else routes to the review panel instead of applying. |
| 3 | Placement | A new page with its own nav link. |
| 4 | Selection | Per-row approve/reject, a "select all" control, and bulk approve/reject actions. |
| 5 | Rejected proposals | Transaction is left exactly as-is; the proposal is discarded with no memory of the rejection — the same category may be proposed again on a future correction. |
| 6 | Ambient notification | A count/badge is shown somewhere prominent (e.g. navigation) whenever pending reviews exist. |

### Assumption made resolving a tension between decisions 1 and 2 (flag for review)

Decision 1's own wording — "review... so you can **bulk-apply**" — describes the broadened, already-categorized bucket as something the user applies, not something the system applies on its own. Auto-applying a change to a transaction that **already has an assigned category** (silently overwriting a prior similarity/LLM/manual decision) is materially riskier than auto-applying to a transaction that's merely `UNSURE`. Given decision 5 also protects against bad auto-applies to the `UNSURE` bucket only by letting the user reject them in-panel — extending silent auto-apply to the higher-risk already-categorized bucket would remove that safety net exactly where it matters most.

**Resolution applied below**: the very-high-confidence auto-apply path (decision 2) applies **only** to the `UNSURE` bucket, matching today's risk profile. Every match against an already-categorized transaction (the new, broadened bucket from decision 1) always goes to the review panel, regardless of confidence. If this isn't what you intended, flag it during the requirements review below — it changes FR-RR-3 and FR-RR-4.

## Functional Requirements

- **FR-RR-1**: When a transaction's category is manually corrected (`PUT /transactions/{id}/category`), the system SHALL search for candidate transactions in two buckets: (a) transactions with `category_source = UNSURE`, and (b) transactions with any other `category_source` whose current category differs from the correction — both compared against the corrected transaction using the existing similarity matcher.
- **FR-RR-2**: Every candidate found SHALL be recorded as a proposal (new entity — see Data Model below), holding at minimum: the source (corrected) transaction, the candidate transaction, the proposed category, the match score, which bucket it came from, and a status.
- **FR-RR-3**: A candidate from the `UNSURE` bucket (FR-RR-1a) whose match score clears a new, higher auto-apply threshold SHALL be applied immediately and automatically, exactly as today's behavior — `category_id` and `category_source = SIMILARITY` are written directly, and the proposal is recorded with status `auto_applied` (visible in the panel as a log, not awaiting action).
- **FR-RR-4**: Every other candidate — `UNSURE`-bucket matches below the auto-apply threshold but at/above the existing similarity threshold, and **all** already-categorized-bucket matches (FR-RR-1b) regardless of score — SHALL be recorded with status `pending` and SHALL NOT be written to the `transactions` table until a user approves it.
- **FR-RR-5**: A new page (own nav entry) SHALL list all `pending` proposals, showing at minimum: candidate transaction (date, description, amount, current category), proposed category, match score/bucket, and the source correction that triggered it.
- **FR-RR-6**: The panel SHALL support per-row approve and reject actions, a "select all" control, and bulk approve/bulk reject over the current selection.
- **FR-RR-7**: Approving a proposal SHALL write the proposed category to the candidate transaction (`category_source = SIMILARITY`) and mark the proposal `approved`.
- **FR-RR-8**: Rejecting a proposal (individually, in bulk, or by never acting on it) SHALL leave the candidate transaction unchanged and mark the proposal `rejected`; no record is kept to suppress the same category being proposed again in a future correction.
- **FR-RR-9**: The app SHALL show a count of `pending` proposals somewhere prominent (e.g. nav badge) whenever the count is greater than zero.
- **FR-RR-10**: The existing `POST /transactions/{id}/category` synchronous single-row update behavior is unchanged — only the downstream sweep behavior changes.

## Non-Functional Requirements

- **NFR-RR-1 (Consistency)**: Proposal generation (FR-RR-1/2) reuses the existing `recategorization_jobs` async mechanism (ingestion-worker polling, not a new synchronous path) — consistent with this project's existing pattern of API service and worker coordinating only through shared database rows.
- **NFR-RR-2 (Data integrity)**: A transaction SHALL never have more than one `pending` proposal for the same candidate+source pair outstanding at once (avoid duplicate proposals piling up if the same correction logic runs more than once).
- **NFR-RR-3 (No new external dependency)**: This feature introduces no new external integration — it extends the existing similarity matcher already in `ingestion-worker`.
- **NFR-RR-4 (Testability)**: Given this project's established practice (all four units have real test suites, and this project treats "verified against live containers" as a completion bar per `audit.md`), the auto-apply/review split and bulk approve/reject paths SHALL have test coverage at the layer they're implemented in, and SHALL be verified against the live stack before this is considered done.

## Deferred to Functional/NFR Design (not requirements-level decisions)

- The exact numeric value of the new higher "auto-apply" threshold, relative to the existing `settings.similarity_threshold`.
- Whether the new proposal entity is a new table (e.g. `recategorization_proposals`, child of `recategorization_jobs`) or a repurposing of the existing table — a new child table is the natural fit given `recategorization_jobs` already represents "one job per correction event," but this is a technical call for Functional Design, not Requirements.
- Exact panel page name/label and its position in the nav.

## Out of Scope

- No changes to the initial categorization path during ingestion (new statements still get similarity match → LLM fallback → `UNSURE`, unchanged).
- No changes to how confidently a transaction is categorized on first ingestion — this feature only affects what happens **after** a manual correction.
