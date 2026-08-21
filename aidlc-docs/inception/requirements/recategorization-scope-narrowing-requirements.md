# Recategorization Scope Narrowing — Requirements

## Intent Analysis Summary

- **User request**: "For recategorisation, do not recategorise those that have been categorised. Limit it to those that's UNSURE or OTHERS. This is because the recategorisation matching is very low in accuracy." (Clarified via follow-up answers: drop the "Others" idea entirely — limit to `UNSURE` only.)
- **Request type**: Enhancement — narrowing existing business logic due to a real observed accuracy problem.
- **Scope estimate**: Single Component (Ingestion Worker Service's Categorization Engine only).
- **Complexity estimate**: Simple (removes one of two existing candidate-scan branches; no new branch, no schema change).

## Background (from live-code research)

- The retroactive recategorization scan (`recategorize_unsure_from_precedent`, `ingestion-worker/src/ingestion_worker/categorization/service.py`), triggered whenever a transaction is manually corrected, currently scans two candidate buckets: **Bucket A** — all `UNSURE` transactions; **Bucket B** — every other transaction in the database regardless of `category_source` (manual/similarity/llm), excluding only the source row and exact-category no-ops. Bucket B is the low-accuracy, noisy source the user wants removed.
- Bucket B matches never auto-apply (WR-10) — they always create a `PENDING` `RecategorizationProposal` with `source_bucket = 'categorized'` for manual review. Bucket A matches can auto-apply above the existing high-confidence threshold.
- `RecategorizationProposalSourceBucket` (Database, `models.py`) has two enum values, `UNSURE` and `CATEGORIZED` — historical proposals already created with `CATEGORIZED` must remain valid and displayable; only the value's *default here-on* production stops.

## Functional Requirements

- **FR-RSN-1 (Remove Bucket B entirely)**: The retroactive recategorization scan no longer scans already-categorized transactions (manual/similarity/llm-sourced) at all. Only `UNSURE` transactions are scanned as candidates going forward (User Answer Q1/Q2 — the originally-proposed "Others" category bucket is explicitly rejected; `UNSURE`-only is the full extent of the new scope).
- **FR-RSN-2 (No change to auto-apply behavior for the surviving bucket)**: `UNSURE`-bucket matching keeps its existing behavior unchanged (auto-apply above the high-confidence threshold, else `PENDING` proposal) — this request only removes the low-accuracy bucket, it doesn't touch the bucket being kept.
- **FR-RSN-3 (Leave existing data alone)**: Any `PENDING` proposals already sitting on the Review page from the old, broader Bucket B scope are left exactly as-is — the user will individually approve/reject them themselves. No backfill, no bulk-reject, no data migration (User Answer Q3).
- **FR-RSN-4 (Scope boundary)**: This change touches only the retroactive recategorization re-scan (`recategorize_unsure_from_precedent`). The separate, unrelated new-transaction ingestion-time categorization logic (`categorize()`, used when a freshly-ingested transaction is first classified via embedding + LLM + similarity) is explicitly untouched (User Answer Q4).

## Non-Functional Requirements

- **NFR-RSN-1 (No schema change)**: `RecategorizationProposalSourceBucket.CATEGORIZED` stays in the enum (historical rows depend on it) — no migration needed.
- **NFR-RSN-2 (No new configuration)**: No new setting is introduced (User Answer Q1 rejected the configurable-category-name idea along with the "Others" bucket itself).
- **NFR-RSN-3 (Dead-code cleanup)**: The now-unused `find_categorized_transactions_excluding` repository query and its corresponding service-layer branch are removed outright, not left dangling or feature-flagged — this project's convention is to delete code once it's genuinely unused rather than leave unreachable branches.

## Summary

Removes the low-accuracy "already-categorized transactions" bucket from the retroactive recategorization re-scan entirely — no replacement bucket, no "Others"-category special-casing. Only `UNSURE` transactions are scanned as recategorization candidates going forward. Existing pending proposals from the old scope are left for manual review, not auto-cleared. No schema change, no new configuration, and no change to the separate ingestion-time categorization path.
