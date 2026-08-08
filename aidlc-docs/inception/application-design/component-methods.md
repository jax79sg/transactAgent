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

### Backup Status Component
*Addendum (2026-08-08, Nightly Transaction Backup feature)*
- `getLatestBackupStatus() -> BackupStatus` (`lastRunAt`, `outcome`: `success`|`failed`, `failureCategory?`: `drive_connectivity`|`other`) — backs the Review page's Backup Status panel (US-7.4)

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

### Currency Conversion Component
- `getRate(fromCurrency, toCurrency='SGD', date) -> {rate, isApproximate, sourceDate} | RateUnavailable`
- `convert(amount, fromCurrency, date) -> ConvertedAmount | Unconverted`

### Ingestion Orchestrator Component
- `processRun(runId) -> void` — the pipeline entry point invoked when a queued run is picked up; iterates files, calls the other Worker components in sequence, updates run/file status as it goes
- `processRecategorizeJob(jobId, sourceTransactionId) -> void` — the FR-5.4 job handler, delegates to Categorization Engine
