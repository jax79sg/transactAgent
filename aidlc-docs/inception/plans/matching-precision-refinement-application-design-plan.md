# Application Design Plan — Matching Precision Refinement

**Role**: Software architect, converting `matching-precision-refinement-requirements.md` into component-level design (no stories this round — requirements were traced directly).

## Genuinely open item

None requiring a new user question — the 8-question round plus 2 clarification rounds already resolved every
product-level decision. What follows are architecture/design decisions at the appropriate altitude for this
stage (component boundaries, method signatures, dependencies, and the one schema-shape decision the
requirements doc explicitly deferred here) — not detailed business rules, which stay deferred to Functional
Design. Each is documented, not asked, consistent with this project's established practice, and flagged here
for correction at the review gate if any reads wrong.

## Key Design Resolution 1: a new, decoupled entity for two-candidate disagreements — not an extension of `RecategorizationProposal`

`RecategorizationProposal` (Epic 6) is structurally tied to a `RecategorizationJob` (a manual-correction
re-scan event) via a `job_id` FK, and carries exactly one `proposed_category_id` per row. A genuine
categorization disagreement (FR-MPR-9) has no triggering `RecategorizationJob` — it arises directly during
ingestion-time `categorize()` — and needs **two** candidate categories (the similarity-sourced one and the
LLM-sourced one), not one. Bending the existing table to fit (nullable `job_id`, a new nullable second
category column, a new `source_bucket` value whose semantics don't match the other two) would overload one
entity with two genuinely different meanings — this project's established precedent leans the other way
(`backup_runs`, the recurring-payments tables, and `embedding_status` were all added as their own
purpose-built shapes rather than folded into an existing entity that didn't quite fit).

**Resolution**: a new Database entity, **`CategorizationDisagreement`** — one row per FR-MPR-9 disagreement,
holding (at the Application Design altitude; exact columns are Database Functional Design's job): the
transaction, the similarity-sourced candidate category, the LLM-sourced candidate category, and a status
(pending / resolved-with-one-of-the-two / rejected). Written by the Ingestion Worker's Categorization Engine
(the only place FR-MPR-6's third bullet — both signals confident, and differ — is detected); read/resolved by
the API Service's existing **Recategorization Review Component** (extended, not a new component — see
Decision 3 below) and surfaced on the existing `/review` page.

Clarification 2's answer ("reuse the `ProposalTable`/`ProposalRow` approve-or-pick-one pattern") is honored at
the **UI/interaction-pattern** level — the same visual/interaction shape, extended to a third row kind — not
by literally reusing the same DB row shape or a single merged list endpoint. Two separate, purpose-fit data
shapes feeding a shared UI component is consistent with how `BackupStatusPanel` (Epic 7) reused the Review
page without merging into `ProposalTable`'s own data model.

## Key Design Resolution 2: the LLM classification moves from an internal last-resort step to an upfront, concurrent, per-file batch step

Today, `categorize(description, amount)` is self-contained: the embedding → fuzzy → LLM → UNSURE chain runs
entirely inside one call, and the LLM only fires if both similarity steps already failed. Three requirements
break that shape:
- FR-MPR-1: the LLM must classify *every* transaction, not just fallback cases.
- FR-MPR-3: when a file has several transactions needing LLM classification, those calls must run
  concurrently, not one-at-a-time.
- FR-MPR-6/FR-MPR-7: the LLM's answer must be **known before** the similarity search's decision is finalized
  — it's used both as a same-transaction agreement signal for the embedding score boost (FR-MPR-7) and to
  detect disagreement against whatever similarity finds (FR-MPR-6). Computing it last, inside `categorize()`,
  can't feed either of those.

**Resolution**: the Categorization Engine gains a new method, `classifyBatch(descriptions, whitelist) ->
Map<description, category|UNSURE>`. The Ingestion Orchestrator's per-file pipeline gains a new upfront step —
batch-classify all of a file's raw transactions' descriptions before the existing per-transaction loop begins
— and `categorize()`'s signature changes to take the already-known `llmCategory` as an input parameter rather
than computing it internally as a last resort. This is a new step on the Orchestrator (already "the only
component that calls the others in sequence"), not a new component.

**Revision (2026-08-16, found live-testing against the user's real local model server during Build and
Test)**: `classifyBatch`'s original internal shape here was "fire one HTTP call per description, concurrently,
bounded by NFR-MPR-1." Live testing showed that still means many simultaneous requests hitting a single local
model server for a large file. Revised to two phases, both still owned by the same `classifyBatch` method (no
change to its external signature or to this resolution's placement in the pipeline): descriptions are grouped
into chunks of a configurable batch size, each chunk classified via a single multi-description prompt/response;
chunks run concurrently (same NFR-MPR-1 cap, now bounding *requests*, not *transactions*); any description a
chunk's response didn't yield a valid answer for falls back to an individual call, only for that description.
See `matching-precision-refinement-requirements.md`'s "Post-Approval Change" section and Ingestion Worker
`business-rules.md` WR-27 for the full reasoning and live-verification numbers.

## Key Design Resolution 3: persist each transaction's own LLM classification

FR-MPR-7's score boost applies to `find_similar_transaction_via_embedding` (fresh, in-memory `llmCategory` is
enough — no persistence needed) but *also* to `recategorize_unsure_from_precedent`, the retroactive re-scan
that runs later, against transactions ingested at some earlier time. For that re-scan's boost to compare a
candidate transaction's own LLM classification against the category being proposed, that classification has
to still be available — which means it must be **persisted**, not just used transiently and discarded.

**Resolution**: add `Transaction.llm_suggested_category_id` (nullable FK to categories; null when the LLM
abstained or the endpoint was unavailable) — a Database Functional Design addition, written once by the
Categorization Engine at ingestion time (FR-MPR-1), read back by the re-scan's boost logic. Same shape as the
existing `embedding_status` field (Epic 9): a thin, purpose-built persisted signal rather than a new table.

## Design Decisions

1. **Recategorization Review Component (API Service) is extended, not duplicated.** A category disagreement
   is, at its core, the same kind of thing this component already owns — human-in-the-loop review of a
   proposed category change — just with two candidates instead of one. New methods: `listPendingDisagreements
   (page) -> DisagreementPage`, `resolveDisagreement(disagreementId, chosenCategoryId) -> UpdatedTransaction`,
   `rejectDisagreement(disagreementId) -> Success`. `getPendingCount()`'s existing single number becomes the
   sum of pending proposals *and* pending disagreements — the nav badge already reads generically as "Review"
   (US-6.6), not "Proposals" specifically, so folding the count together needs no badge redesign.
2. **No bulk actions for disagreements.** `bulkApprove`/`bulkReject` exist for single-candidate proposals
   because "approve" has one unambiguous meaning. A disagreement has no sensible bulk default — resolving it
   always means a specific, individual choice between two different categories. Disagreements are
   individual-action only; `BulkActionBar` is unaffected.
3. **Resolving a disagreement writes `category_source` from whichever candidate was chosen** (`similarity` or
   `llm`), not `manual` — the human picked between two system-computed suggestions, they didn't type a
   category from scratch. Mirrors how approving an existing proposal already writes `category_source =
   similarity` (FR-RR-7).
4. **Categorization Engine and Recurring Payment Manager both gain the price-bucket-in-embedding-text change
   (FR-MPR-4) and the score-boost logic (FR-MPR-7)** — the same shared Vector Store Client / embedding
   machinery (Epic 9) is reused, no new component. Exactly how the boost applies at each of the four call
   sites (`find_similar_transaction_via_embedding`, `recategorize_unsure_from_precedent`,
   `matchNewTransaction`, `runDetectionScan`'s group-merge pass) differs in shape — each has a different
   notion of "the candidate's known category" — and is left to Ingestion Worker Functional Design, consistent
   with this stage's altitude (method signatures and component boundaries, not per-call-site business rules).
5. **Frontend**: no new component. `ProposalTable`/`ProposalRow` (Epic 6) are extended to render a third row
   kind (two candidate categories, pick-one-or-reject actions) alongside the existing single-candidate
   approve/reject rows, fed by the new `listPendingDisagreements` endpoint — same "one Frontend SPA component
   covering every page" convention as every prior addendum.
6. **No new external dependency and no new container.** The new local model
   (`mlx-community/gemma-4-26b-a4b-it-4bit`) is served by the same already-configured, already-external
   `OPENROUTER_BASE_URL` endpoint category — only the model name changes (env value, not a new setting).

## Execution Checklist

- [x] Update `components.md`: Categorization Engine addendum (batch classification, disagreement detection);
  Recurring Payment Manager addendum (price bucket + boost); Recategorization Review Component addendum
  (disagreement review); Frontend SPA addendum (disagreement rows); Shared Data Store addendum (new
  `CategorizationDisagreement` entity, `Transaction.llm_suggested_category_id` field)
- [x] Update `component-methods.md`: `classifyBatch` (new), `categorize()` signature change, `findSimilar
  PastTransaction`/`recategorizeUnsureFromPrecedent`/`matchNewTransaction`/`runDetectionScan` addenda;
  Recategorization Review Component's 3 new methods
- [x] Update `services.md`: Ingestion Orchestrator's new upfront per-file batch-classify step
- [x] Update `component-dependency.md`: dependency-matrix row for the new entity's readers/writers
- [x] Update `application-design.md`: consolidated summary addendum + FR-MPR traceability table (no stories
  this round — traced directly to FR-MPR-1..12)
- [x] Update `aidlc-state.md`

## Mandatory Artifacts
- [x] `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`,
  `application-design.md` — all updated in place with dated addenda (this project's established pattern for
  post-completion changes, preserving prior history untouched)
