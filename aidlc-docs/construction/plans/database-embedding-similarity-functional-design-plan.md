# Functional Design Plan — Database Unit: Local Embedding-Based Semantic Similarity

Unit: Database. Scope: one new field on the existing `Transaction` entity (FR-6/FR-7/FR-11) — no new
entity, since the embedding vector itself lives in the separate Vector DB (Application Design), not
Postgres.

## Genuinely open item
None — Application Design already resolved the field's purpose and its role in unifying forward processing
with the one-time backfill (single default value, no separate backfill table/flag). This stage just gives
it a concrete lifecycle and business rule.

## Steps
- [x] Add `embedding_status` (enum: `pending`|`completed`, default `pending`) to the `Transaction` entity in
  `domain-entities.md`, with an addendum explaining why one default serves both forward processing (FR-6)
  and the historical backfill (FR-11).
- [x] Add **BR-24** to `business-rules.md`: one-way, two-state transition, no `failed` state (transient
  failures just leave a row `pending`, per FR-10), application-layer enforced by the Ingestion Worker's
  Embedding Manager Component.
- [x] Add a **Lifecycle: Transaction.embedding_status** section to `business-logic-model.md`, explicitly
  noting it's a pure processing-status field with no semantic claim (contrast with `category_source`).

## Mandatory Artifacts
- [x] `domain-entities.md` — updated in place
- [x] `business-rules.md` — updated in place (BR-24)
- [x] `business-logic-model.md` — updated in place
