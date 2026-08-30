# Code Generation Plan — Ingestion Worker Service — Recategorization Algorithm Rework

## Unit Context
- **Unit**: Ingestion Worker Service (existing unit, brownfield — modify in place, no new files except one DB migration and any new test files)
- **Workspace root**: `/Users/jax/projects/transactAgent` (application code at workspace root, never under `aidlc-docs/`)
- **Rules implemented**: WR-35 (broadened precedent pool), WR-36 (direction signal), WR-37 (delimiter-based ID stripping), WR-38 (threshold reconciliation), WR-39 (full re-embedding backfill, vectors only)
- **Dependencies**: None on other units — Database unit gets one retroactively-added migration (same precedent as `0012_reembed_after_price_bucket_text_change.py`), no API Service/Frontend SPA changes
- **Out of scope**: FR-RAR-2 (LLM verification gate) — deferred, no code generated for it

## Steps

- [x] **Step 1 — Business Logic Generation: `embedding/text.py`** (WR-36, WR-37)
  - Change `build_embedding_text(description, amount)` → `build_embedding_text(description, amount, direction)`
  - Add reference-code stripping: strip everything from the first case-insensitive occurrence of `"OTHR-"`, `"OTHR - "`, or `"REF:"` onward, before building the final string
  - Output format: `f"{cleaned_description} | {price_bucket_label(amount)} | {direction}"`

- [x] **Step 2 — Business Logic Generation: `categorization/service.py`** (WR-35, wiring for WR-36)
  - Add a `_transaction_direction(txn)` helper (mirrors the existing `_transaction_amount(txn)`): returns `"outflow"` if `out_flow is not None` else `"inflow"`
  - `find_similar_transaction_via_embedding`: add a `direction` parameter, threaded into its `build_embedding_text` call
  - `categorize()`: add a `direction` parameter (the caller, `orchestrator/pipeline.py`, has `raw_txn.direction.value` — `"out"`/`"in"` — before the `Transaction` row exists; map to `"outflow"`/`"inflow"`), threaded into its `find_similar_transaction_via_embedding` call
  - `recategorize_unsure_from_precedent`: redesign per WR-35 —
    - Replace the current single-pairwise `_find_match` embedding branch with: query `query_nearest_neighbors` for the candidate's top-`embedding_top_k` neighbors in the `transactions` collection, fetch full rows via `get_similarity_candidates_by_ids`, filter to `category_name == proposed_category.name`, take the best-scoring match among those (apply the existing amount-range gate + WR-30 boost logic to each, same as today)
    - Fuzzy-text fallback: replace the single `source_candidate` list passed to `find_best_match` with `list_similarity_candidates(db)` filtered to `category_name == proposed_category.name`
    - Thread `direction` through both the source transaction's and each candidate's `build_embedding_text` calls

- [x] **Step 3 — Business Logic Generation: `recurring_payments/service.py`** (wiring for WR-36, no algorithm change)
  - Add a local `_transaction_direction(txn)` helper (same shape as Step 2's)
  - `_embedding_candidate_scores`: add a `direction` parameter, threaded into its `build_embedding_text` call; its caller (`match_new_transaction`) supplies the transaction's own direction
  - `_merge_groups_via_embedding`: thread `direction` through, derived from each representative `Transaction`
  - `RecurringPayment`-keyed calls (none in this file directly build embedding text for a bare `RecurringPayment` — confirm during implementation; if any exist, default direction to `"outflow"` since `RecurringPayment` has no direction field of its own and this domain's recurring payments are overwhelmingly outgoing — documented inline as an explicit implementation decision, not a schema change)

- [x] **Step 4 — Business Logic Generation: `embedding/service.py`** (wiring for WR-36)
  - `process_next_embedding_batch`: thread direction through the `Transaction` call site (`txn.out_flow`/`txn.in_flow`, same derivation as Step 2's helper); the `RecurringPayment` call site defaults to `"outflow"` per Step 3's reasoning

- [x] **Step 5 — Configuration: reconcile threshold** (WR-38)
  - Remove (or update to `0.82`) the `EMBEDDING_SIMILARITY_THRESHOLD=0.75` line in `.env`, reconciling it with `config.py`'s coded default

- [x] **Step 6 — Database Migration** (WR-39)
  - Create `database/migrations/versions/0016_reembed_after_direction_and_id_stripping_text_change.py`, following `0012_reembed_after_price_bucket_text_change.py`'s exact pattern: plain `UPDATE transactions SET embedding_status = 'pending' WHERE embedding_status = 'completed'` and the equivalent for `recurring_payments`; no-op downgrade, same reasoning as 0012
  - Explicit in the migration docstring: this touches `embedding_status` only, never `category_id`/`category_source` (WR-39's hard constraint)

- [x] **Step 7 — Business Logic Unit Testing**
  - `test_embedding_text.py`: new tests for `direction` parameter output, and for the ID-stripping heuristic (each of the three delimiters, case-insensitivity, and a negative case confirming genuine payee names with digits are NOT stripped when no delimiter is present)
  - `test_categorization_service.py`: update existing `find_similar_transaction_via_embedding`/`categorize`/`recategorize_unsure_from_precedent` tests for the new `direction` parameter; new tests for WR-35's broadened-pool behavior (multiple neighbors returned, only the category-matching one selected; no match when no neighbor is in the corrected category even if a closer neighbor of a different category exists)
  - `test_recurring_payments_service.py`: update for the new `direction` parameter, confirm no behavior change to matching/merge logic itself
  - `test_embedding_service.py`: update `process_next_embedding_batch` tests for the new `direction` parameter

- [x] **Step 8 — Business Logic Summary**
  - Write `aidlc-docs/construction/ingestion-worker/code/recategorization-algorithm-rework-summary.md` documenting what changed, mirroring this project's established per-feature code summary convention

## Story/Requirement Traceability
FR-RAR-1 → Step 2. FR-RAR-3/FR-RAR-5 → Step 5. FR-RAR-6 → Steps 1-4. FR-RAR-7 → Step 1. NFR-RAR-3 → Step 6. All steps → Step 7 (tests) and Step 8 (summary).

This plan is the single source of truth for this unit's Code Generation — execution proceeds step-by-step in the order above.
