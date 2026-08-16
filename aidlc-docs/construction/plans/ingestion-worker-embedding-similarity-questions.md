# Ingestion Worker Service — Functional Design Questions (Local Embedding-Based Semantic Similarity, Epic 9)

## Question 1
`matchNewTransaction` and `runDetectionScan` (Recurring Payment Manager) both need to query stored
`RecurringPayment.name` embeddings from the vector store's `recurring_payment_names` collection. But the
Database unit's Functional Design for this feature only added an `embedding_status` field to `Transaction` —
nothing tracks when a `RecurringPayment`'s name embedding should be computed/stored. `RecurringPayment` CRUD
(create/rename) happens synchronously in the API Service, which never calls the embedding endpoint or vector
store itself (that's Ingestion Worker Service-only, per the one hard architectural rule). How should
`RecurringPayment` name embeddings actually get into the vector store?

A) Retroactive Database addition: add an `embedding_status` field to `RecurringPayment` (new migration,
same pattern as this project's prior mid-feature retroactive Database additions, e.g. Epic 8's
`DetectionScanRun`), processed by the same unified `Embedding Manager.processNextEmbeddingBatch()` poll-cycle
mechanism as `Transaction` — one mechanism handles both entity types (Recommended: matches the Application
Design's stated principle of "one unified, idempotent, backlog-driven mechanism," and keeps the "async,
eventually-consistent" model consistent across both entity types)

B) No persistence: recompute embeddings for the full active `RecurringPayment` register in memory every time
`matchNewTransaction`/`runDetectionScan` needs to search it, and compare via in-process cosine similarity —
no new Database field, no vector-store writes for this collection at all (viable since the register is
small — tens of rows, not transaction-table volume — but means the `recurring_payment_names` "collection" in
`component-methods.md` is really just an in-memory computation, not an actual stored vector-DB collection,
and re-embeds the same names repeatedly on every match attempt)

C) Write-through-on-miss: the Worker computes and upserts a `RecurringPayment`'s embedding into the vector
store the first time a lookup finds it missing (lazy population, no new Database field), and never
re-embeds it again afterward — meaning a later rename would silently keep matching against the old, stale
name embedding forever, since nothing would trigger a re-embed

D) Other (please describe after [Answer]: tag below)

[Answer]:A
