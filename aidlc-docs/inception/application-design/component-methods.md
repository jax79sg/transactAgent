# Component Methods — Bank Transaction Insights App

High-level method signatures per component. Types are conceptual (language-agnostic); exact types are finalized in Functional Design (per-unit, Construction phase). Detailed business rules (e.g., similarity threshold, exact fallback ordering edge cases) are also deferred to Functional Design.

---

## API Service

### Auth Component
- `login(username, password) -> SessionToken | AuthError`
- `validateSession(token) -> UserIdentity | Unauthenticated` — used by request middleware on every protected route

### Transaction Management Component
- `listTransactions(filters: {dateRange, bank, category, flowDirection, currency, textSearch}, groupBy?, sortBy?, page) -> TransactionPage`
- `getTransaction(transactionId) -> TransactionDetail` (includes original + converted amount, conversion-approximate flag)
- `correctCategory(transactionId, newCategory) -> UpdatedTransaction` — sets `category_source = manual`, then calls `IngestionTriggerComponent.enqueueRecategorizeJob(sourceTransactionId)`
- `exportCsv(filters, groupBy?, sortBy?) -> CsvFileStream`
- *Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*: `listTransactions`/`getTransaction`'s return shape gains `embeddingStatus` (FR-7, US-9.1) — read directly from the Shared DB, no new method needed.

### Dashboard/Insights Component
- `getCategoryTrends(dateRange, currency?) -> CategoryTrendSeries[]`
- `getCashFlow(dateRange) -> CashFlowSeries`
- `getBankBreakdown(dateRange) -> BankBreakdown[]`
- `getConversionDisclosure(dateRange, scope) -> {approximateCount, excludedCount, excludedTransactionIds}`

### Ingestion Trigger & Status Component
- `startIngestionRun() -> RunId` — enqueues a run record for the Worker; rejects if a run is already in progress
- `getRunStatus(runId) -> RunStatus` (found/processed/skipped/failed counts, per-file detail, overall state)
- `listRunHistory(page) -> RunSummary[]`
- `enqueueRecategorizeJob(sourceTransactionId) -> JobId` — internal method, called by Transaction Management Component per FR-5.4

### Recategorization Review Component
*Addendum (2026-08-02, Recategorization Review Panel feature)*
- `listPendingProposals(page) -> ProposalPage` — includes candidate transaction summary, proposed category, match score/bucket, triggering correction
- `getPendingCount() -> integer` — backs the nav badge (US-6.6)
- `approveProposal(proposalId) -> UpdatedTransaction` — writes the proposed category to the candidate transaction, marks proposal `approved`
- `rejectProposal(proposalId) -> Success` — leaves the candidate transaction untouched, marks proposal `rejected`, no suppression record kept (FR-RR-8)
- `bulkApprove(proposalIds) -> {approved: [], failed: []}`
- `bulkReject(proposalIds) -> {rejected: []}`
- *Addendum (2026-08-16, Matching Precision Refinement feature)*:
  - `listPendingDisagreements(page) -> DisagreementPage` — includes candidate transaction summary, both candidate categories (similarity-sourced, LLM-sourced)
  - `resolveDisagreement(disagreementId, chosenCategoryId) -> UpdatedTransaction` — `chosenCategoryId` must be one of the two offered candidates; writes it to the transaction with `category_source` set to whichever origin (`similarity`|`llm`) the chosen candidate came from (Design Decision 3), marks the disagreement resolved
  - `rejectDisagreement(disagreementId) -> Success` — leaves the transaction `UNSURE`, marks the disagreement rejected, no suppression record kept (same policy as `rejectProposal`)
  - `getPendingCount()`'s existing return value now sums pending proposals *and* pending disagreements (Design Decision 1) — no new method, same signature
  - No bulk variants for disagreements (Design Decision 2)

### Backup Status Component
*Addendum (2026-08-08, Nightly Transaction Backup feature)*
- `getLatestBackupStatus() -> BackupStatus` (`lastRunAt`, `outcome`: `success`|`failed`, `failureCategory?`: `drive_connectivity`|`other`) — backs the Review page's Backup Status panel (US-7.4)

### Recurring Payments Component
*Addendum (2026-08-08, Recurring Payments feature — Epic 8)*
- `listRecurringPayments() -> RecurringPayment[]`
- `createRecurringPayment(name, expectedAmount, frequency, dueMonth?, dueDay, categoryId?) -> RecurringPayment`
- `updateRecurringPayment(id, ...fields) -> RecurringPayment`
- `deleteRecurringPayment(id) -> Success`
- `bulkImportRecurringPayments(rows: {name, amount, frequency, dueMonth?, dueDay}[]) -> {created: RecurringPayment[], failed: {row, reason}[]}` — NFR-4 per-row isolation
- `listPendingMatches() -> RecurringPaymentMatch[]`
- `approveMatch(matchId) -> RecurringPaymentMatch` — marks the cycle Paid, sets the payment's `is_trusted = true`
- `rejectMatch(matchId) -> Success` — no side effects (FR-8)
- `listDetectionSuggestions() -> DetectionSuggestion[]`
- `dismissDetectionSuggestion(id) -> Success` — sticky (FR-13)
- `addFromDetectionSuggestion(id, overrides?) -> RecurringPayment`
- `getStatusSummary() -> {dueSoonCount, overdueCount, pendingMatchCount, newSuggestionCount}` — backs the Dashboard section and the nav badge (US-8.3/8.7)

### Configuration Component
- `listCategories() -> Category[]`
- `addCategory(name) -> Category`
- `renameCategory(categoryId, newName) -> Category` — cascades rename to existing transactions referencing it
- `removeCategory(categoryId) -> Success | BlockedInUseError`

---

## Ingestion Worker Service

### Drive Connector Component
- `ensureAuthenticated() -> Success | ReauthRequiredError`
- `listFolderPdfFiles() -> DriveFileRef[]` (id, name, modifiedTime)
- `downloadFile(driveFileRef) -> PdfBytes`
- *Addendum (2026-08-08, Nightly Transaction Backup feature)*:
  - `ensureBackupFolderExists(parentFolderId) -> FolderId` — idempotent; creates the `backup` subfolder under the dedicated backup Drive folder if it doesn't already exist
  - `uploadFile(folderId, filename, bytes, mimeType) -> DriveFileRef`
  - `listBackupFolderFiles(folderId) -> DriveFileRef[]` (id, name, createdTime) — used by retention (`enforceRetention`)
  - `deleteFile(driveFileRef) -> Success`

### Backup Manager Component
*Addendum (2026-08-08, Nightly Transaction Backup feature)*
- `isBackupDueNow() -> boolean` — true when today's backup hasn't run yet and either the scheduled time has passed, or this is startup catch-up (FR-8)
- `runBackup() -> BackupRunResult` — exports all transactions to CSV, uploads via Drive Connector, calls `enforceRetention`, records a `backup_runs` row (outcome + failure category if applicable); does not retry within the same invocation beyond the Drive Connector's existing transient-error retries (FR-9: no next-day-early retry is a caller-level/scheduling concern, not this method's)
- `enforceRetention(folderId) -> {deletedCount}` — keeps the 7 most recent backup files (by creation time), deletes the rest; only considers files matching this feature's own naming convention (NFR-4)

### Duplicate Detection Component
- `computeFileHash(pdfBytes) -> Hash`
- `isAlreadyProcessed(hash) -> boolean`
- `recordProcessed(hash, driveFileId, statementMetadata) -> Success`

### Statement Extraction Component
- `extractText(pdfBytes) -> RawText` (includes OCR fallback internally when no selectable text is found)
- `parseTransactions(rawText) -> {bankName, currency, transactions: RawTransaction[]} | ExtractionFailed(reason)`

### Categorization Engine Component
- `categorize(transactionDescription, context: {bankName, amount}) -> {category, source: 'similarity'|'llm'|'unsure', confidence}`
  - Internally: `findSimilarPastTransaction(description) -> PrecedentMatch | None` (prioritizes `category_source = manual` precedents per FR-5.3)
  - Internally: `classifyWithLlm(description, whitelist) -> category | UNSURE`
- `recategorizeUnsureFromPrecedent(correctedTransactionId) -> {updatedTransactionIds: []}` — the FR-5.4 retroactive job handler
  - *Addendum (2026-08-02, Recategorization Review Panel feature)*: broadened and split. Internally: `findRecategorizationCandidates(correctedTransactionId) -> {unsureMatches: [], categorizedMatches: []}` (US-6.1); UNSURE matches clearing the new auto-apply threshold are applied directly as before (US-6.2); every other match — lower-confidence UNSURE, and *all* `categorizedMatches` regardless of score — creates a pending proposal row instead of writing to `transactions` (US-6.3). Method's external contract (called by the API Service via the async job queue, per `services.md`) is unchanged; only its internal behavior and side effects change.
  - *Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*: `findSimilarPastTransaction` (and its `findRecategorizationCandidates` counterpart) now internally: (1) computes a transient, non-persisted query embedding of the description via `EmbeddingManager.computeEmbedding()`; (2) if that succeeds, calls `VectorStoreClient.queryNearestNeighbors(vector, collection='transactions', ...)`; (3) if a result clears the new embedding-similarity threshold, uses it exactly as a fuzzy-text match would be (same amount-gate + manual-precedence rules, FR-5/NFR-1/US-9.3); (4) otherwise — including when step (1) fails (FR-10) — falls through to the existing fuzzy-text `find_best_match` unchanged (FR-3).
  - *Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)*:
    - New: `classifyBatch(descriptions: string[], whitelist) -> Map<description, category|UNSURE>` — groups descriptions into configurable-size chunks, classifies each chunk in one multi-description prompt, runs chunks concurrently bounded by a configurable cap, and falls any description a chunk's response didn't validly answer back to an individual per-description call (also concurrent, same cap) — see Key Design Resolution 2's 2026-08-16 revision for why this replaced a simpler one-call-per-description design. Called once per file by the Ingestion Orchestrator's new upfront pipeline step (see `services.md`), not by `categorize()` itself.
    - Changed: `categorize()`'s signature becomes `categorize(transactionDescription, context: {bankName, amount}, llmCategory: category|UNSURE) -> {category, source: 'similarity'|'llm'|'unsure', matchedCandidateCategory?}` — the LLM classification is now an input (already computed by `classifyBatch`), not something this method computes internally as a last resort (FR-MPR-1/6). Its decision: `findSimilarPastTransaction`'s result and `llmCategory` agree → auto-assign as before; one is present/confident and the other abstains (`UNSURE`) or is absent (no similarity match) → the confident one wins, auto-assigned directly (Clarification 1); both present and differing → genuine disagreement, no auto-assignment — instead calls the new `recordDisagreement` below (FR-MPR-6/9).
    - New: `recordDisagreement(transactionId, similarityCategory, llmCategory) -> DisagreementId` — writes a `CategorizationDisagreement` row (Key Design Resolution 1); the transaction's own `category_source` stays `UNSURE` until a human resolves it via the API Service's `resolveDisagreement`/`rejectDisagreement`.
    - Changed: `findSimilarPastTransaction`'s embedded query text now includes a price-range bucket alongside the description (FR-MPR-4), and its candidate scoring receives a small boost when a candidate's actual category agrees with `llmCategory` (FR-MPR-7) — exact boost mechanics deferred to Functional Design (Design Decision 4).
    - Changed: at the end of ingestion-time categorization, the transaction's own `llmCategory` (whatever `classifyBatch` returned for it, including `UNSURE`) is persisted to `llm_suggested_category_id` (Key Design Resolution 3), so `recategorizeUnsureFromPrecedent`'s own boost logic (below) can read it back later for transactions ingested in an earlier run.
    - Changed: `recategorizeUnsureFromPrecedent`'s pairwise embedding comparison also gets the price-bucket embedding text (FR-MPR-4) and a small score boost when the *candidate* transaction's persisted `llm_suggested_category_id` agrees with the category being proposed (FR-MPR-7) — this method does **not** gain a disagreement-review branch (FR-MPR-12: disagreement-routing is scoped to `categorize()`'s ingestion-time decision only).

### Currency Conversion Component
- `getRate(fromCurrency, toCurrency='SGD', date) -> {rate, isApproximate, sourceDate} | RateUnavailable`
- `convert(amount, fromCurrency, date) -> ConvertedAmount | Unconverted`

### Ingestion Orchestrator Component
- `processRun(runId) -> void` — the pipeline entry point invoked when a queued run is picked up; iterates files, calls the other Worker components in sequence, updates run/file status as it goes
- `processRecategorizeJob(jobId, sourceTransactionId) -> void` — the FR-5.4 job handler, delegates to Categorization Engine

### Recurring Payment Manager Component
*Addendum (2026-08-08, Recurring Payments feature — Epic 8)*
- `matchNewTransaction(transaction) -> void` — called from `_persist_transaction()` right after a transaction is saved; finds active Recurring Payments with an unresolved current cycle whose description/category is a similarity match and whose due-date window covers the transaction's date; for a never-yet-approved payment always creates a pending match (FR-6); for a trusted payment, auto-applies when the amount is within tolerance of expected, else still creates a pending match (FR-7)
- `isDetectionScanDueNow() -> boolean` — time-based due-check, same shape as Backup Manager's `isBackupDueNow()`
- `runDetectionScan() -> void` — scans transaction history for monthly-cadence repeating charges (similar description/category + amount, ≥2 occurrences ~30 days apart) not covered by any existing Recurring Payment and not matching a previously-dismissed pattern; records new `DetectionSuggestion` rows
- *Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*: Both methods' description/category similarity check now tries `VectorStoreClient.queryNearestNeighbors(vector, collection='recurring_payment_names', ...)` first (same query-embedding-then-fallback pattern as the Categorization Engine addendum above), falling back to the existing fuzzy-text matcher when nothing clears the embedding threshold or the endpoint is unreachable (FR-4/FR-10). No change to the trust/tolerance decision logic itself (Epic 8) — only how a candidate is *found*.
  - *Correction (2026-08-12, retroactively during Ingestion Worker Service Functional Design — see `ingestion-worker-embedding-similarity-functional-design-plan.md`)*: the sentence above over-generalized. Only `matchNewTransaction` queries `collection='recurring_payment_names'` (it's genuinely matching a transaction's description against `RecurringPayment.name` values). `runDetectionScan` has no `RecurringPayment` in its own grouping step (WR-19 groups *transactions with each other*; it only consults `RecurringPaymentMatch` — a DB join, not a vector search — afterward, to exclude already-covered patterns) — its embedding-first step queries `collection='transactions'` instead, mirroring the Categorization Engine's usage of that same collection. See `business-rules.md` (Ingestion Worker unit) WR-22 for the formalized rule.
  - *Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)*: Both methods' embedded query text now includes a price-range bucket (FR-MPR-4). `matchNewTransaction`'s candidate scoring gets a small boost when a Recurring Payment's own `category` (Epic 8, AR-15..20 — optional) agrees with the newly-ingested transaction's `llmCategory` (already computed by the Categorization Engine's `classifyBatch` for this same transaction, passed through). `runDetectionScan`'s group-merge pass gets a boost too, using each side's persisted `llm_suggested_category_id`/actual category as available — exact mechanics deferred to Functional Design (Design Decision 4). Neither method gains a disagreement-review branch (FR-MPR-12).

### Vector Store Client Component
*Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*
- `upsertEmbedding(collection: 'transactions'|'recurring_payment_names', entityId, vector) -> Success`
- `queryNearestNeighbors(vector, collection: 'transactions'|'recurring_payment_names', filters: {excludeEntityId?}, topK) -> {entityId, similarityScore}[]`

### Embedding Manager Component
*Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*
- `computeEmbedding(text) -> Vector | EmbeddingUnavailable` — calls the configured oMLX endpoint with the raw, unnormalized text (FR-9); used both by this component's own batch below and, transiently/non-persisted, by the Categorization Engine and Recurring Payment Manager at query time (see the plan doc's "Key Design Resolution")
- `processNextEmbeddingBatch() -> {processedCount}` — the poll-cycle handler (fifth `poll_once()` branch, see `services.md`): selects a bounded batch of transactions with `embedding_status = pending`, computes + persists (via Vector Store Client) each one's embedding, updates `embedding_status`; serves both newly-ingested transactions (FR-6) and the one-time historical backfill (FR-11) as the same mechanism. Stops early for the cycle on an endpoint-unavailable error rather than burning through the whole batch on doomed calls (FR-10); already-processed transactions are never revisited, and an interrupted batch simply resumes next cycle (NFR-4).
  - *Addendum (2026-08-12, retroactively during Ingestion Worker Service Functional Design)*: also selects a bounded batch of `RecurringPayment` rows with `embedding_status = pending` (Database `BR-25`, added retroactively) and processes them the same way, targeting the `recurring_payment_names` collection — one unified mechanism draining both entity types' backlogs, not two separate handlers.
