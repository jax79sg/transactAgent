# Domain Entities (Internal DTOs) — Unit 3: Ingestion Worker Service

No new persisted entities — this unit reads/writes Unit 1's schema. These are internal, transient pipeline data shapes.

**Addendum (2026-08-02, Epic 6)**: `RecategorizationProposal` (Unit 1's schema) is written directly by the broadened re-scan (WR-9/WR-10) via `categorization/repository.py`, the same way the existing re-scan already writes `Transaction` rows directly — no new internal DTO is introduced here, matching the existing pattern of this module not modeling its own transient shape for simple repository writes.

## `RawExtractedStatement`
- `bank_name: str | None`
- `currency: str | None`
- `confidence: "high" | "medium" | "low"` (or numeric — finalized in NFR Design/Code Generation)
- `transactions: list[RawExtractedTransaction]`
- `extraction_error: str | None` (set on schema-validation or LLM-call failure)

## `RawExtractedTransaction`
- `transaction_date: date`
- `description: str`
- `amount: Decimal`
- `direction: "in" | "out"`
- `printed_converted_amount_sgd: Decimal | None` (Clarification 2a — captured when the statement itself shows an SGD equivalent)
- `confidence: "high" | "medium" | "low"`

## `CategorizationResult`
- `category_name: str` (a whitelist name, or the literal "UNSURE")
- `source: "similarity" | "llm" | "unsure"`
- `matched_precedent_transaction_id: UUID | None` (set when `source = "similarity"`, for traceability/debugging)
- `llm_suggested_category_name: str | None` *(added 2026-08-16, Matching Precision Refinement, WR-28)* — the always-on LLM's own classification for this transaction, regardless of which source ultimately decided `category_name`; `None` when the LLM abstained (`UNSURE`) or its endpoint was unreachable. The caller (`_persistTransaction`) resolves this to `Transaction.llm_suggested_category_id` (Database `BR-26`).
- `disagreement: DisagreementInfo | None` *(added 2026-08-16, Matching Precision Refinement, WR-28)* — set only when `categorize()` hit the genuine-disagreement branch; carries what the caller needs to write a `CategorizationDisagreement` row (Database `BR-27`) after the transaction itself is persisted (a `CategorizationDisagreement` needs a real `transaction_id`, which doesn't exist yet at the point `categorize()` is called — see `DisagreementInfo` below).

## `DisagreementInfo` *(added 2026-08-16, Matching Precision Refinement)*
- `similarity_category_name: str`
- `llm_category_name: str`
- `similarity_score: float` (0-100 scale, same as `CategorizationResult`/`RecategorizationProposal.match_score`)
- Purpose: `categorize()` itself has no `Transaction.id` to write a `CategorizationDisagreement` row against yet (the transaction isn't constructed until after `categorize()` returns, in `_persistTransaction`) — this DTO carries the disagreement forward so the Orchestrator can record it immediately after `db.flush()`s the new transaction, same two-step pattern already used for `matchNewTransaction` (also called only after the transaction has a real ID).

## `ConversionResult`
- `converted_amount_sgd: Decimal | None`
- `is_approximate: bool`
- `is_unavailable: bool`
- `fx_rate_used_id: UUID | None`
- `source: "statement_printed" | "identity_sgd" | "fx_api_exact" | "fx_api_fallback" | "unavailable"` (internal-only, for logging/debugging — not persisted as a separate DB column; `is_approximate`/`is_unavailable`/`fx_rate_used_id` on the `Transaction` row capture what the API/Frontend need per Unit 1's schema)

## `RunProgressUpdate`
- Internal shape the Orchestrator uses to update `IngestionRun` counters after each file — not a new entity, just a note that these are incremental updates (`files_processed_count += 1`, etc.), not a full row replace, so concurrent reads (Unit 2's status polling) always see monotonically-increasing progress.

**Addendum (2026-08-08, Nightly Transaction Backup, Epic 7)**: No new internal DTO is introduced. The Backup Manager writes directly to Unit 1's `BackupRun` schema, matching this module's existing pattern of not modeling a separate transient shape for a simple repository write (same reasoning already used for `RecategorizationProposal`). The CSV export itself is a direct column-for-column dump of `Transaction` rows (WR-13) — not a transformed/derived shape worth naming as its own DTO.

**Addendum (2026-08-08, Recurring Payments, Epic 8)**: No new internal DTO is introduced. The Recurring Payment Manager writes directly to Unit 1's `RecurringPaymentMatch`/`DetectionSuggestion` schemas, same reasoning as above. The only transient shape worth naming informally is a candidate-grouping structure inside `runDetectionScan` (transactions grouped by normalized description pending cadence/count checks) — internal to that one function, not shared across components, so not modeled as a named DTO here.

**Addendum (2026-08-12, Local Embedding-Based Semantic Similarity, Epic 9)**: Two small transient shapes are worth naming since they're shared across components (Vector Store Client's return type, consumed by both Categorization Engine and Recurring Payment Manager):

## `Vector`
- Opaque, fixed-dimension float array (exact dimensionality follows `google/embeddinggemma-300m`, confirmed at NFR Requirements) — never persisted directly on a `Transaction`/`RecurringPayment` row (only the separate Vector DB stores the vector itself, keyed by entity ID; the row only carries `embedding_status`).

## `EmbeddingUnavailable`
- Sentinel return value from `Embedding Manager.computeEmbedding()` (not an exception — WR-25 requires this path to never raise) signaling the oMLX endpoint was unreachable or errored for this call. Every caller (WR-21's four call sites, and `processNextEmbeddingBatch`) treats this identically: fall through to the fuzzy-text path, or leave the row `pending` for the batch job.

No new DTO is introduced for `queryNearestNeighbors`'s return shape (`{entityId, similarityScore}[]`) — it's simple enough, and scoped enough to the one method, that naming it separately would add a layer without adding clarity, matching this module's existing convention (e.g. `ConversionResult`'s sibling shapes above were named only when reused; `RunProgressUpdate` was explicitly called out as *not* a new entity for the same reason).
