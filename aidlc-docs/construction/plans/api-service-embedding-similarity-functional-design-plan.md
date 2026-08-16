# Functional Design Plan — API Service Unit: Local Embedding-Based Semantic Similarity (Epic 9)

## Genuinely open item
None requiring a new user question. Scope is narrower than originally scoped at Application Design, though:
the Ingestion Worker Service unit's Code Generation surfaced a real requirement this unit's Application Design
addendum didn't anticipate (see below), flagged there for this stage rather than silently assumed.

## Scope
1. **`embedding_status` exposure** (as originally scoped, `components.md`): `TransactionDTO`
   (`listTransactions`/`getTransaction`) gains a read-only `embeddingStatus` field, sourced directly from the
   Shared DB. This component never calls the Vector Store Client or embedding endpoint itself (Ingestion
   Worker-only, per the one hard architectural rule).
2. **`RecurringPayment.embedding_status` write path** (new — surfaced during Ingestion Worker Code Generation,
   `embedding-similarity-summary.md`, Database `BR-25`): since the Ingestion Worker Service is the only
   component that ever computes/persists an embedding, and `RecurringPayment.name` can be edited via this
   unit's own CRUD (FR-1), something has to reset `embedding_status` back to `pending` whenever a payment is
   created or its `name` changes — otherwise a rename would leave the vector store permanently stale (BR-25's
   entire reason for existing). This unit's Recurring Payments Component is the only writer of
   `RecurringPayment` rows, so it's the natural (and only possible) place for this reset — not a new product
   decision, just closing a gap Application Design's Epic 9 addendum didn't cover for this unit.

## Steps
- [ ] Add **AR-21** to `business-rules.md`: `embeddingStatus` is read-only, sourced directly from the DB
  column, no new query logic beyond an added `SELECT` column.
- [ ] Add **AR-22** to `business-rules.md`: create sets `embedding_status = pending` (matches the column's own
  default, stated for completeness); any update that changes `name` resets it to `pending`; an update that
  doesn't touch `name` (`expectedAmount`, `dueDay`, `categoryId`, etc.) MUST NOT reset it.
- [ ] Addendum to `business-logic-model.md`'s Transaction Management Component section (embedding_status
  exposure) and Recurring Payments Component section (CRUD bullet, reset-on-rename)
- [ ] `domain-entities.md`: add `embeddingStatus` to `TransactionDTO`

## Mandatory Artifacts
- [x] `business-rules.md` — updated in place (AR-21, AR-22)
- [x] `business-logic-model.md` — updated in place
- [x] `domain-entities.md` — updated in place
