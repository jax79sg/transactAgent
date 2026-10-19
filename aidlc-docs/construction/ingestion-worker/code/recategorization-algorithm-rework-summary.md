# Recategorization Algorithm Rework — Code Summary

Implements WR-35 through WR-39 (`business-rules.md`). Scope: broaden the retroactive re-scan's precedent pool, rework the shared embedding-text construction (direction signal + reference-code stripping), reconcile a threshold divergence, and backfill existing embeddings. The independent LLM verification gate originally scoped alongside this (FR-RAR-2) was explicitly deferred by the user before Code Generation — no code exists for it.

## Files Modified

| File | Change |
|---|---|
| [`embedding/text.py`](../../../../ingestion-worker/src/ingestion_worker/embedding/text.py) | `build_embedding_text` gains a `direction` parameter (WR-36) and strips text after the first `"OTHR-"`/`"OTHR - "`/`"REF:"` delimiter, case-insensitive, before embedding (WR-37) |
| [`categorization/service.py`](../../../../ingestion-worker/src/ingestion_worker/categorization/service.py) | New `_transaction_direction` helper; `categorize()`/`find_similar_transaction_via_embedding` thread `direction` through; `recategorize_unsure_from_precedent`'s `_find_match` redesigned around a category-filtered vector-store nearest-neighbor search (WR-35) replacing the old single-pairwise comparison; unused `SimilarityCandidate`/`cosine_similarity` imports removed |
| [`orchestrator/pipeline.py`](../../../../ingestion-worker/src/ingestion_worker/orchestrator/pipeline.py) | `_persist_transaction` derives `direction` from `raw_txn.direction.value` and passes it to `categorize()` |
| [`recurring_payments/service.py`](../../../../ingestion-worker/src/ingestion_worker/recurring_payments/service.py) | New `_transaction_direction` helper; `_embedding_candidate_scores` always passes `"outflow"` (see design note below); `_merge_groups_via_embedding` threads each representative's real direction |
| [`embedding/service.py`](../../../../ingestion-worker/src/ingestion_worker/embedding/service.py) | `process_next_embedding_batch` threads direction through both the `Transaction` and `RecurringPayment` (always `"outflow"`) branches |
| [`.env`](../../../../.env) | `EMBEDDING_SIMILARITY_THRESHOLD` reconciled from `0.75` back to the code default `0.82` (WR-38) |

## Files Created

| File | Purpose |
|---|---|
| [`database/migrations/versions/0016_reembed_after_direction_and_id_stripping_text_change.py`](../../../../database/migrations/versions/0016_reembed_after_direction_and_id_stripping_text_change.py) | WR-39: resets every `completed`-status `Transaction`/`RecurringPayment` row back to `pending`, following `0012`'s exact prior precedent. Plain single-column `UPDATE` — never touches `category_id`/`category_source` |

## Design Decision Made During Code Generation

`recurring_payments/service.py`'s `_embedding_candidate_scores` (queries the `recurring_payment_names` collection) always passes `direction="outflow"` for its query text, rather than the querying transaction's real direction. Reasoning: `RecurringPayment` has no direction field of its own, so every vector already stored in that collection (`embedding/service.py`) was embedded assuming `"outflow"`. Passing a transaction's true direction here (occasionally `"inflow"`, e.g. a refund) would introduce a silent, systematic mismatch against every stored vector in that space — unrelated to what this feature is trying to improve. Not asked as a question given during Functional Design planning this was already flagged as a low-stakes implementation decision to resolve during Code Generation, per the approved plan.

## Tests

- `tests/test_embedding_text.py`: rewrote `TestBuildEmbeddingText` for the 3-arg signature; new `TestReferenceCodeStripping` (5 tests — each delimiter, case-insensitivity, negative case confirming a genuine payee name with digits and no delimiter is untouched)
- `tests/test_categorization_service.py`: updated all `categorize()`/`find_similar_transaction_via_embedding` call sites for the new `direction` parameter; rewrote the recategorization embedding test to mock `query_nearest_neighbors` (WR-35 replaced the old direct-pairwise-cosine approach, which no longer exists to mock); added 2 new tests — broadened-pool matching against a precedent other than the just-corrected transaction, and correct rejection of a closer-but-wrong-category neighbor
- `tests/test_recurring_payments_service.py`: fixed one test's mock lookup dict to include the new direction token in its keys (`test_does_not_merge_when_below_similarity_threshold`); other embedding-related tests needed no changes (they assert on return values, not on the exact text passed to `compute_embedding`)
- `tests/test_embedding_service.py`: updated 2 `assert_called_once_with(...)` exact-text assertions for the new direction suffix

## What Was Not Verified in This Step

This machine's `ingestion-worker/.venv` has a broken Python interpreter symlink (points to a `/usr/local/bin/python3` that no longer exists on this system) — the test suite could not actually be executed during Code Generation. Verified instead: `py_compile` on every modified/created file (clean, no syntax errors) and a manual trace of every `build_embedding_text`/`find_similar_transaction_via_embedding`/`categorize()` call site repo-wide to confirm no stale signature usage remains. Actually running the suite, along with fixing the broken venv, is deferred to Build and Test.
