# Functional Design Plan — Ingestion Worker Service Unit: Local Embedding-Based Semantic Similarity (Epic 9)

Unit: Ingestion Worker Service. Scope: two new components (Vector Store Client, Embedding Manager), and
embedding-first-then-fuzzy-fallback addenda to two existing components (Categorization Engine, Recurring
Payment Manager) — component boundaries and method signatures already fixed at Application Design
(`components.md`, `component-methods.md`, `services.md`). This stage turns those into concrete algorithms,
new `WR-*` business rules, and a `business-logic-model.md` addendum, the same altitude as the Backup Manager
(Epic 7) / Recurring Payment Manager (Epic 8) sections already in this unit's docs.

## Genuinely open item — requires a question

While reconciling `component-methods.md`'s Epic 9 addenda against the Database unit's actual Functional
Design output for this feature, I found a real gap, not just an architecture-altitude derivation:

- `Vector Store Client.queryNearestNeighbors(vector, collection='recurring_payment_names', ...)` is called by
  both `matchNewTransaction` and `runDetectionScan` (`component-methods.md`) — meaning `RecurringPayment.name`
  embeddings must already be computed and stored in that collection for the query to find anything.
- But the **only** persisted embedding-tracking mechanism that exists is `Transaction.embedding_status`
  (Database unit Functional Design, 2026-08-11) — `RecurringPayment` has no equivalent field, and
  `Embedding Manager.processNextEmbeddingBatch()` (`component-methods.md`) is scoped explicitly to
  "transactions with `embedding_status = pending`." Nothing in the approved design says when, or how, a
  `RecurringPayment`'s name embedding gets computed and written to the vector store in the first place.

This is a genuine, unresolved product/architecture decision — not something a rereading of already-approved
docs resolves on its own — so I'm asking rather than assuming, per this stage's directive to default to
asking on real ambiguity.

**See `ingestion-worker-embedding-similarity-questions.md` — Question 1.**

## Documented resolutions (architecture-altitude derivation, not asked — flagged for correction if wrong)

1. **`runDetectionScan`'s own grouping queries the `'transactions'` collection, not `'recurring_payment_names'`.**
   `component-methods.md`'s "Both methods... tries `queryNearestNeighbors(..., collection='recurring_payment_names', ...)`"
   phrasing conflates two different things: `matchNewTransaction` genuinely matches a transaction's
   description against `RecurringPayment.name` values (correct target: `recurring_payment_names`), but
   `runDetectionScan`'s own algorithm (WR-19, unchanged by this feature) groups **transactions with each
   other** ("group recent transactions by normalized description/category + similar amount") — it has no
   `RecurringPayment` in the loop at all until the later "not already covered by a `RecurringPayment`'s
   matches" filter, which is a DB join against `RecurringPaymentMatch`, not a vector search. So
   `runDetectionScan`'s embedding-first step (FR-4) queries `'transactions'`, mirroring the Categorization
   Engine's own usage of that same collection — not a new, third collection, just the existing one applied to
   a second call site. Treating this as a documented correction of imprecise Application Design wording, not
   a new product decision.
2. **Candidate selection shape**: `queryNearestNeighbors` returns a bounded top-K (K deferred to NFR
   Requirements/Code Generation, same precedent as `similarity_threshold`'s exact value), not just the single
   nearest neighbor — because FR-5 requires an embedding-found candidate to go through *exactly* the same
   amount-gate (`amounts_in_range`) and manual-source-precedence (WR-3) filtering the fuzzy-text matcher
   already applies, and the nearest neighbor by raw cosine distance might not be the nearest neighbor that
   *passes* those filters. The Worker fetches the K candidates' full rows (needs `category_source`/`amount`,
   which the vector store doesn't hold), applies the same filters used today, and takes the best-scoring
   survivor; if none of the K survive, that's "no embedding candidate" and it falls through to fuzzy-text
   (FR-3) — exactly as if the embedding step found nothing.
3. **Self-exclusion**: `filters: {excludeEntityId?}` (already in the approved method signature) is used
   whenever the query subject is itself a stored candidate (the retroactive re-scan's source transaction, and
   `runDetectionScan`'s own grouping) — mirrors the existing self-exclusion already required for the
   fuzzy-text path (BR-15/US-6.1), not a new rule.
4. **Backfill/batch processing order**: `processNextEmbeddingBatch()` processes pending rows in a
   deterministic order (ascending `created_at`/`id`) so an interrupted-and-resumed batch (NFR-4) makes visible
   forward progress rather than an arbitrary/re-shuffled subset each cycle. Batch size itself stays deferred
   to NFR Requirements/Code Generation.
5. **Write ordering for `processNextEmbeddingBatch`**: for each transaction, `Vector Store Client.upsertEmbedding`
   is called before `Transaction.embedding_status` is flipped to `completed` — `upsertEmbedding` is idempotent
   (same transaction ID overwrites its own vector), so a crash between the two steps just leaves the row
   `pending` and it's safely reprocessed (re-upserts the same vector) next cycle, consistent with NFR-4.

## Steps

- [ ] Resolve Question 1 (RecurringPayment embedding trigger) via `ingestion-worker-embedding-similarity-questions.md`
- [ ] Add new `WR-*` business rules to `business-rules.md` covering: embedding-first-then-fallback decision
  order (FR-3/FR-4/FR-5, applied identically at both call sites), the amount-gate/manual-precedence carryover
  (NFR-1), raw/unnormalized text into the embedder (FR-9), soft-fail/no-badge-on-failure (FR-10), the
  `processNextEmbeddingBatch` batch/backfill mechanics (FR-6/FR-11/NFR-4), and whatever Question 1 resolves to
  for `RecurringPayment` embeddings
- [ ] Add **Vector Store Client Component** and **Embedding Manager Component** sections to
  `business-logic-model.md` (algorithm-level pseudocode, same style as the existing Backup Manager/Recurring
  Payment Manager sections), plus addenda to the existing Categorization Engine and Recurring Payment Manager
  sections showing the embedding-first-then-fallback step inline in their pipelines
- [ ] `domain-entities.md`: add any new internal (non-persisted) DTOs needed — e.g. a `Vector`/
  `EmbeddingUnavailable` shape, a `NearestNeighborCandidate` shape — following this unit's existing convention
  of only naming a DTO when it's shared across components, not for single-function-local shapes

## Mandatory Artifacts
- [ ] `business-rules.md` — updated in place
- [ ] `business-logic-model.md` — updated in place
- [ ] `domain-entities.md` — updated in place (if any new internal DTO is warranted)
