# Functional Design Plan — Ingestion Worker Service — Recategorization Algorithm Rework

## Context
Unit: Ingestion Worker Service (existing unit, reused — Units Generation was skipped for this change). Scope per the approved requirements/execution plan: FR-RAR-1 (broader precedent pool), FR-RAR-3/5 (threshold tuning/reconciliation), FR-RAR-6/7 (embedding-text rework: direction signal + ID-stripping). FR-RAR-2 (LLM gate) is deferred, out of scope.

## Plan

- [x] Step 1: Design the broader-precedent-pool retrieval strategy for `recategorize_unsure_from_precedent` (replaces the current single-pairwise `_find_match`) — approach approved as-is (WR-35)
- [x] Step 2: Design the ID-stripping heuristic for `build_embedding_text` (FR-RAR-7) — revised to delimiter-based stripping per user feedback (WR-37)
- [x] Step 3: Design the direction-signal addition to `build_embedding_text` (FR-RAR-6) — WR-36
- [x] Step 4: Resolve threshold values (FR-RAR-3, FR-RAR-5) — reconcile `.env` to code default only, no further changes this pass (WR-38)
- [x] Step 5: Resolve the NFR-RAR-3 stale-vector/backfill decision — REVISED: full backfill following WR-32's precedent, vectors only (WR-39); user explicitly clarified assigned categories must not change as a side effect
- [x] Step 6: Write `business-logic-model.md`, `business-rules.md`, `domain-entities.md` addenda — business-logic-model.md and business-rules.md updated (WR-35..39 + deferred-LLM-gate note); domain-entities.md unchanged (no new entities/fields introduced by this rework)

## Proposed Design (for review)

### Step 1 — Precedent pool retrieval

**Investigated feasibility first**: the Qdrant vector-store points carry no payload metadata (just `id` + `vector`, see `vector_store.py`'s `upsert_embedding`) — there's no category filter available at the Qdrant query layer today. Adding one would mean a schema/payload change plus re-indexing everything, which is more scope than this rework's embedding-accuracy focus calls for.

**Recommended approach**: for each `UNSURE` candidate, query the `transactions` vector-store collection for its top-`embedding_top_k` nearest neighbors (reusing `query_nearest_neighbors`, same as `categorize()`'s `find_similar_transaction_via_embedding` already does), fetch their full rows (`get_similarity_candidates_by_ids`, already exists), then filter to only those whose `category_name` equals the category the source transaction was just corrected to, and take the best-scoring one among those (if any). This directly implements "broader precedent pool" — instead of checking resemblance to one specific transaction, it checks resemblance to the best-matching *real example* of that category anywhere in history — while reusing 100% existing retrieval infrastructure (no new Qdrant payload work, no new query mechanism). The fuzzy-text fallback (`find_best_match`) gets the equivalent treatment: build its candidate list from `list_similarity_candidates(db)` filtered to the corrected category, instead of the current single `source_candidate`.

### Step 2 — ID-stripping heuristic

Evidence from the rejected-proposal examples shows the noisy substrings are consistently long alphanumeric reference codes, usually appended after a delimiter (` OTHR-...`, `OTHR - ...`) or embedded mid-string (`DICNP17537901512105MMHTZ8`, `EPOSSPSPTWM8J GOJ IIFTRGNB`, `qsb-sqr-sg-382501037048`). **Recommended heuristic**: strip tokens that are (a) 8+ characters, AND (b) a mix of letters and digits with no spaces (i.e. match something like `\b[A-Za-z0-9]{8,}\b` where the token contains at least one digit) — this catches reference codes while leaving genuine merchant/payee names (which are almost always pure-letter words, e.g. `NOVALAND`, `HITPAY`, `Askalamoonzxs`) untouched. Applied before building the embedded text, not to the stored `description` field itself (the raw description stays intact everywhere else — UI display, LLM classification input, etc. — only the embedding-text builder's *output* changes).

### Step 3 — Direction signal

Mechanical, per FR-RAR-6: append `"outflow"` or `"inflow"` (mirroring the existing price-bucket suffix style) based on whether the transaction's `out_flow` or `in_flow` field is set. `build_embedding_text` currently takes `(description, amount)` — needs a third parameter for direction, or the two amount-bearing call-site patterns (`out_flow if out_flow is not None else in_flow`) get replaced with passing both flow fields (or a bool) through. Low ambiguity — implementation detail for Code Generation, not asked below.

### Step 5 — Stale-vector / backfill decision (NFR-RAR-3)

Two real options, needs your call:
- **Accept the temporary mismatch**: old vectors lack the direction token and stripped-ID text until each row is next re-embedded (which currently only happens once, at creation — see `process_next_embedding_batch`'s `pending`-only scan). Since direction/ID-stripping are just one or two tokens among the full description, old vectors likely still work "well enough" during a transition period, imperfectly.
- **Force a backfill**: reset all already-embedded `Transaction`/`RecurringPayment` rows back to a `pending` embedding state (or add a one-off script) so `process_next_embedding_batch` re-embeds everything with the new text format on the next poll cycles. More thorough, but touches every historical row and takes time proportional to your transaction volume through the existing batch job.

## Questions

### Question 1: Precedent pool retrieval approach
Does the Step 1 recommended approach (reuse existing vector-store top-K search + category filter, no new Qdrant payload/schema work) match what you had in mind for "broaden the precedent pool"?

A) Yes — use the recommended approach as described

B) No — I want category-aware filtering built directly into the vector store (payload metadata + native Qdrant filter), even though it means a larger schema/re-indexing change

C) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 2: ID-stripping heuristic
Does the Step 2 recommended heuristic (strip 8+ character alphanumeric tokens containing at least one digit) sound right, or should it be more/less aggressive?

A) Yes — use the recommended heuristic as described

B) More aggressive — also strip shorter alphanumeric tokens (lower the length threshold)

C) Less aggressive — only strip tokens following an obvious delimiter pattern (e.g. after "OTHR-", "OTHR - ", "REF:") rather than any alphanumeric-with-digit token anywhere in the string

D) Other (please describe after [Answer]: tag below)

[Answer]:C

### Question 3: Threshold values (FR-RAR-3, FR-RAR-5)
Current thresholds: `similarity_threshold=85.0` (fuzzy-text eligibility), `embedding_similarity_threshold=0.82` in code but `0.75` live in `.env` (embedding eligibility), `recategorization_auto_apply_threshold=97.0` (auto-apply bar). Given the precision-first goal, how should these be set?

A) Reconcile `.env` back to the code default (0.82) and leave the other threshold values as-is for now — let the retrieval-strategy and ID-stripping changes do the precision work first, re-tune numbers later based on real results

B) Reconcile `.env` to 0.82 AND raise it further (recommend a specific value based on the evidence — I'll analyze the rejected-proposal score distribution and propose one)

C) I'll provide specific target values myself (describe after [Answer]: tag below)

D) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 4: Stale-vector / backfill decision (NFR-RAR-3)
Per Step 5 above — accept the temporary mismatch, or force a backfill of all existing embeddings?

A) Accept the temporary mismatch — simplest, no extra work, rows naturally correct themselves over time as they're touched again (if ever)

B) Force a backfill — build a mechanism to re-embed all existing `Transaction`/`RecurringPayment` rows under the new text format as part of this rework

C) Other (please describe after [Answer]: tag below)

[Answer]:A
