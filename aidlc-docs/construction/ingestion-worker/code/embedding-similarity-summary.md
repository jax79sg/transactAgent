# Embedding Manager / Vector Store Client — Code Summary (Epic 9)

New package: [`ingestion_worker/embedding/`](../../../../ingestion-worker/src/ingestion_worker/embedding/).

| File | Purpose |
|---|---|
| `client.py` | `EmbeddingClient` — calls the user-managed oMLX endpoint (`openai` SDK, OpenAI-compatible embeddings route), no retry, single 5s attempt, soft-fails to `None` on any error (WR-25) |
| `vector_store.py` | `VectorStoreClient` — `qdrant-client` wrapper: `ensure_collections()`, `upsert_embedding()`, `query_nearest_neighbors()`; same soft-fail philosophy, plus the non-blocking-startup pattern |
| `similarity.py` | Pure `cosine_similarity()` — the PBT-eligible split-out counterpart to the I/O-bound calls above (NFR-3) |
| `repository.py` | Pending-backlog queries + status-flip writes for both `Transaction` and `RecurringPayment` |
| `service.py` | `process_next_embedding_batch()` — the poll-cycle handler (WR-26) |

Integration changes: `categorization/service.py` (`find_similar_transaction_via_embedding`, embedding-first in `categorize()`, embedding pairwise check inlined in `recategorize_unsure_from_precedent()`), `recurring_payments/service.py` (`_embedding_candidate_payment_ids`, embedding-first in `match_new_transaction()`, `_merge_groups_via_embedding` in `run_detection_scan()`), `main.py` (`vector_store.ensure_collections()` at startup, `poll_once()`'s fifth branch), `categorization/similarity.py` (`select_best_match` extracted so both the fuzzy and embedding paths apply WR-3's manual-precedence rule identically).

## Real design gaps found and fixed during Functional Design → Code Generation

These weren't caught until reconciling the approved Application Design against what the code actually needed to do — each is documented in `business-rules.md`/`business-logic-model.md` with a dated correction, not silently changed:

1. **`RecurringPayment` had no embedding-tracking field at all.** Application Design's `component-methods.md` assumed a `recurring_payment_names` vector-store collection existed without specifying what populates it. Resolved (user-answered question, Functional Design) by retroactively adding `RecurringPayment.embedding_status` to the Database unit (`BR-25`, migration `0010`) — reusing the `embeddingstatus` enum type `0009` already created. Unlike `Transaction.embedding_status`, this field has **two** write paths: the Ingestion Worker (this unit) writes `completed`; the API Service (Unit 2, not yet built as of this summary) will need to reset it to `pending` on create/rename — flagged for that unit's own Functional Design.
2. **`runDetectionScan` doesn't call the fuzzy-text matcher at all.** The original Epic 9 Application Design addendum assumed WR-19's grouping used `find_best_match` (like the Categorization Engine) and just needed an embedding-first swap. Reading the actual code showed WR-19 groups transactions by **exact** normalized-description string equality (`_normalize_description`, a dict-key grouping, unrelated to `find_best_match`/WR-20). Redesigned during Code Generation: the exact-match grouping stays the primary, unchanged mechanism; a new `_merge_groups_via_embedding` pass additively merges two distinct groups when their most-recent transactions' embeddings clear the threshold (direct pairwise `cosine_similarity`, not a vector-store search — the candidate pool is the small number of distinct patterns per scan, not the full transaction history).
3. **Fuzzy scores (0-100) and cosine similarity (0.0-1.0) are different scales.** `recategorize_unsure_from_precedent`'s bucket-split logic compares `match.score` against `recategorization_auto_apply_threshold` (97.0). An embedding-sourced match feeding a raw 0.0-1.0 cosine value into that comparison would never auto-apply. Fixed by rescaling every embedding-sourced `SimilarityMatch.score` to the same 0-100 range (`cosine_similarity * 100`) before it's used anywhere outside the eligibility check itself — proven by a dedicated regression test (`test_embedding_pairwise_match_auto_applies_above_rescaled_threshold`) that would fail without the rescale.
4. **`matchNewTransaction`'s per-payment loop needed a whole-operation, not per-candidate, fallback semantic.** `_embedding_candidate_payment_ids` collapses "embedding endpoint down" and "embedding search found zero candidates" into the same `None` sentinel — both mean "check every payment via fuzzy-text instead," matching WR-21 step 4's framing as a fallback for the whole search, not a per-payment retry.

## Real bugs found via the test suite (not live infra — see note below)

- None beyond the design gaps above — every new code path is covered by the test suite described below, first-pass-clean once the corrections above were made.

## Tests

- `tests/test_embedding_similarity.py` (new): 8 tests incl. 3 Hypothesis property tests for `cosine_similarity`
- `tests/test_embedding_client.py` (new): 6 tests — unset config, success, raw/unnormalized text (WR-24), connection/timeout soft-fail with no retry, empty-vector response
- `tests/test_embedding_vector_store.py` (new): 10 tests — collection creation/skip/never-raises, upsert success/failure, query nearest-first/exclude/unavailable/empty-vs-None
- `tests/test_embedding_repository.py` (new): 7 tests — pending selection, limit, deterministic order, mark-embedded for both entity types
- `tests/test_embedding_service.py` (new): 7 tests — both entity types, stop-early on endpoint/vector-store failure, no-op when nothing pending
- `tests/test_categorization_service.py`: +11 tests — embedding search (threshold/amount-gate/stale-entry), embedding-first-then-fuzzy-fallback ordering in `categorize()`, embedding pairwise auto-apply with rescaled score in the recategorization re-scan
- `tests/test_recurring_payments_service.py`: +6 tests — embedding-first matching, whole-operation fallback, group-merge (positive, embedding-unavailable, below-threshold)
- `tests/test_main_loop.py`: +4 tests — fifth-branch dispatch priority

Full suite: **233/233 passing** (up from 179).

## What was NOT live-verified in this unit's Code Generation

Unlike prior features, this unit's Code Generation did not rebuild/redeploy the live stack — the new `vector-db` `docker-compose` service and `qdrant-client`/`query_points` API usage were smoke-tested against a real, temporarily-run `qdrant/qdrant:latest` container during Infrastructure Design/here (confirmed `query_points`, not the deprecated `search`, is this client version's real method; confirmed point IDs round-trip as UUID strings; confirmed the image has neither `wget` nor `curl`, informing the healthcheck fix). Full live verification of the whole stack together (migration `0010`, the new `vector-db` service, graceful degradation with `EMBEDDING_BASE_URL` unset) is deferred to the feature's Build and Test stage, after the API Service and Frontend SPA units are also complete.
