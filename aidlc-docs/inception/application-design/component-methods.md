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
- *Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: `getRunStatus`'s per-file detail gains the outcome value `skipped_probable_duplicate` and two fields, `comparisonId?` and `matchedStatementLabel?` (so the Frontend can render "probable duplicate of <statement>" and link to the comparison, US-14.2). No new method.

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
- **Addendum (2026-08-16, Configurable Application Settings feature — see `configurable-app-settings-application-design-plan.md`)**:
  - `listSettings() -> SettingDTO[]` — every in-scope setting's name, current effective value, owning service (`ingestion-worker`/`api-service`), classification (`standard`/`advanced`), and type/range metadata (FR-CAS-1/2/3). Only ever returns names on the static allow-list — never consults or enumerates anything outside it.
  - `getSetting(name) -> SettingDTO | NotFoundError` — `NotFoundError` for any name not on the allow-list, including every excluded secret (NFR-CAS-2) — indistinguishable from a genuinely-unknown name, so no information about which names are "secret vs. just unknown" leaks through the error itself.
  - `updateSetting(name, newValue) -> SettingChangeResult | ValidationError | NotFoundError` — validates `newValue` against the setting's real type/range (FR-CAS-8) before doing anything else; on success, writes to the shared override-settings file (never root `.env`, FR-CAS-4), records a `SettingChange` history row (FR-CAS-9), and returns the restart guidance (below) for the owning service. Nothing is written on validation failure.
  - `getRestartGuidance(settingName) -> RestartGuidance` — owning service, the exact restart command, and (only when the owning service is `ingestion-worker`) a busy/idle read via `isIngestionWorkerBusy()` (Key Design Resolution 2). `api-service`-owned settings get no busy/idle field at all (US-10.3's third edge case) — not a `false`/`unknown` placeholder, the field is simply absent, since the concept doesn't apply there.
  - `listSettingHistory() -> SettingChangeDTO[]` — every persisted `SettingChange` row, most recent first (FR-CAS-9, US-10.4).
  - `isIngestionWorkerBusy() -> bool` — internal helper backing `getRestartGuidance`; a read-only Shared DB query for any `ingestion_runs`/`recategorization_jobs` row with `status = 'running'` (Key Design Resolution 2) — no call to the Ingestion Worker Service itself, no new table.

### Background Activity Component
*Addendum (2026-08-18, Background Process Visibility feature — see `background-process-visibility-application-design-plan.md`)*
- `getActivitySummary() -> {current: CurrentActivity | null, recent: RecentActivityEntry[]}` — single endpoint backing both the nav bar indicator and the detail panel (FR-BPV-7). `current` is `null` when idle (FR-BPV-4); when set, it identifies the job type (`ingestion_run` | `recategorization_job`, FR-BPV-5) and its `startedAt`. `recent` is a bounded, most-recent-first list of completed ingestion runs and recategorization jobs (job type, `completedAt`) — exact bound (count/window) is a Functional Design decision (FR-BPV-3/6). Read-only — a purpose-built sibling to `isIngestionWorkerBusy()` above, not a reuse of it, since this needs job-type identification and history that helper doesn't provide.

### Account Management Component
*Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)* — signatures only; validation and merge rules are Functional Design.
- `listAccounts() -> AccountSummary[]` — each `{id, name, bankName, accountIdentifier?, type: 'deposit'|'credit_card'|'unknown', currency, anchor?: {balance, asOfDate}, statementCount}`; backs the account management UI and the "anchor required" prompt (US-13.1/13.2/13.3).
- `renameAccount(accountId, newName) -> Account`
- `mergeAccounts(survivingAccountId, absorbedAccountId, keepAnchorFrom?: accountId) -> Account | MergeRefused(reason: 'currency_mismatch' | 'anchor_choice_required')` — reassigns the absorbed account's statements to the survivor and removes the absorbed account; never drops an anchor silently (US-13.2, A-6).
- `setAccountType(accountId, type: 'deposit'|'credit_card'|'unknown') -> Account` (US-13.2, A-3)
- `setAnchor(accountId, balance, asOfDate) -> Anchor | ValidationError` — deposit accounts only; replaces any existing anchor (one active anchor per account, A-6); rejects a non-numeric balance or a future `asOfDate` (US-13.3).

### Balance Component
*Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)* — all read-only, computed on request, nothing stored.
- `balanceFromAnchor(anchorBalance, anchorDate, targetDate, netFlowBetween) -> Decimal` — **pure function** (the property-based-testing target, NFR-AB-4): given the anchor and the signed net flow (inflows − outflows) strictly between the two dates (up to and including the later one), returns the end-of-day balance at `targetDate`, adding the net flow when `targetDate` is on or after `anchorDate` and subtracting it when before (FR-AB-7). Exact decimal arithmetic only (NFR-AB-1).
- `getBalances(query: {date} | {month}) -> {resolvedDate, ingestedThroughDate, accounts: {accountId, name, currency, balanceNative?, balanceSgd?, status: 'ok'|'anchor_required'|'fx_unavailable', isApproximate}[], combinedTotalSgd, excluded: {accountId, reason}[]}` — I/O wrapper around the pure function: gathers each deposit account's net flow, converts via `lookupFxRateAsOf`, resolves a month to its last day (today for the in-progress month, A-5), and names every account excluded from the combined total (FR-AB-9/10/11/14, A-8).
- `getBalanceSeries(range: {from, to}) -> {points: {date, combinedSgd?, perAccount: Map<accountId, Decimal?>}[], missingAccounts: {accountId, reason}[]}` — every point equals what `getBalances` returns for that date (US-13.5); point granularity (daily vs month-end) is a Functional Design decision; a date with no usable FX rate is a gap for that account, never a guess.
- `listDiscrepancies() -> {accountId, statementId, closingDate, printedBalance, computedBalance, difference}[]` — only for accounts with an anchor and statements with a printed closing balance; the mismatch tolerance is a Functional Design decision (A-4).
- `lookupFxRateAsOf(fromCurrency, date) -> {rate, rateDate, isApproximate} | RateUnavailable` — internal helper, **cache-only** (Question 1 = A): the nearest `fx_rate_cache` rate for `fromCurrency` → SGD dated on or before `date`; `isApproximate` is true when `rateDate != date`; `RateUnavailable` when none exists. Deliberately distinct from the Ingestion Worker's Currency Conversion `getRate`, which may fetch from an external service — this one never does.

### Duplicate Review Component
*Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)* — signatures only; wording, state transitions, and endpoint paths are Functional Design. All writes are small synchronous row writes; the removal itself is executed by the Ingestion Worker, never here.
- *(Amended 2026-10-04, Ingestion Worker FD Q1 = C)*: `PairView` gains `removalOffered: boolean` (the worker's stored `removal_allowed`; false means information only: dismiss, no remove) and the preview gains `onlyOnRemovedCopy` (transactions with no match on the kept copy); `confirmRemoval` also returns `Refused(reason: 'removal_not_offered')`.
- `listProbablePairs() -> PairView[]` — each `{pairId, comparisonId, keep: StatementLabel, remove: StatementLabel, correctionsOnKept, correctionsOnRemoved, removalPreview: {transactions, dependentRows: Map<kind, count>, correctionsLost}, removalStatus?: 'pending'|'embeddings_pending'|'done'|'failed', failureReason?}`; `keep`/`remove` are the worker's stored proposal, displayed and never recomputed (US-14.5); the correction counts and preview are read live.
- `getPendingPairCount() -> {count}` — pairs awaiting a decision; backs the nav badge (US-14.5), same shape as the recategorization pending-count.
- `getComparison(comparisonId) -> ComparisonView` — `{sides: [{label: {fileName, bank, period}, transactionCount, shown: SnapshotRow[]}, ...], matchedCount, reason, state}`, `SnapshotRow = {date, description, amount, direction, marker: 'also_on_other'|'only_on_this_one'}`, `state` one of `skipped`, `ingest_at_next_run`, `ingested_at_your_request`, `pair_pending`, `removed`; reads only stored snapshots, so it is unchanged if the original later changes (US-14.2).
- `confirmRemoval(pairId, acknowledged: {removeStatementHash, correctionsLost}) -> RemovalJobId | Refused(reason: 'already_requested'|'pair_not_pending')` — writes a removal job carrying what the user saw, for the worker to re-verify (US-14.6).
- `dismissPair(pairId) -> Success` — remembered by the pair (A-PD-5); idempotent.
- `overrideSkippedFile(comparisonId) -> Success` — writes the "not a duplicate" decision against the skipped file's content hash; ingested at the next run (FR-PD-7, A-PD-4); idempotent.
- `requestRecheck() -> Success` — asks the worker to re-scan the held statements.
- `getScanStatus() -> {lastCheckedAt?, recheckRequested}` — lets the panel say when it last looked.

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
- *Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13)*: `statementMetadata` gains `accountId` (from the Account Resolver) and an optional `closingBalance: {amount, asOfDate}`. Hash computation and the duplicate check are unchanged.
- *Scope change (2026-10-03)*: `statementMetadata` no longer carries `accountId` or a closing balance. New: `recordStatementAccounts(statementId, resolvedSections) -> StatementAccountId[]` — one row per account section (the account, and its optional `closingBalance: {amount, asOfDate}`), returned so each persisted transaction can link to its section.
- *Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: `lookupRememberedFile(hash) -> RememberedFile | None`, `RememberedFile = {state: 'probable_duplicate'|'overridden'|'confirmed_duplicate', matchedStatementHash?, comparisonId?}` — called after `isAlreadyProcessed` returns false and before extraction; not gated by the detection switch (it honours past decisions). `isAlreadyProcessed`, `computeFileHash`, and `recordProcessed` are unchanged.

### Statement Extraction Component
- `extractText(pdfBytes) -> RawText` (includes OCR fallback internally when no selectable text is found)
- `parseTransactions(rawText) -> {bankName, currency, transactions: RawTransaction[]} | ExtractionFailed(reason)`
- *Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13)*: `parseTransactions`'s result gains three optional statement-level fields — `accountIdentifier?`, `accountType?: 'deposit'|'credit_card'|'unknown'`, and `closingBalance?: {amount, asOfDate}` (FR-AB-2/4/5). A missing field never makes extraction fail (A-2, A-3); the closing balance is never emitted as a `RawTransaction`, and the existing balance-line exclusion is unchanged (NFR-AB-3).
  - *Scope change (2026-10-03)*: the three fields are per **account section**. `parseTransactions`'s result becomes `{bankName, statementDate, confidence, sections: AccountSection[]} | ExtractionFailed(reason)` with `AccountSection = {accountIdentifier?, accountType?, currency, closingBalance?, transactions: RawTransaction[]}`; a flat reply with no sections is accepted as one implicit section, and a section with no currency falls back to the statement's primary currency (neither: the existing WR-2 failure).

### Probable Duplicate Detector Component
*Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)* — signatures only; the matching tolerance, the period-overlap definition, and the threshold values are Functional Design, calibrated against the live statements (NFR-PD-1).

*Pure functions — the property-based-testing targets (NFR-PD-7); no I/O:*
- `matchTransactions(a: TxnKey[], b: TxnKey[]) -> {matched: (indexA, indexB)[]}` — **one-to-one**: each transaction pairs with at most one on the other side, so repeated identical transactions are not double counted; `TxnKey = {date, amount, direction, description}`, description compared with the wording tolerance.
- `matchRatio(matchedCount, countA, countB) -> Decimal` — `matchedCount / min(countA, countB)`, in [0, 1]; 0 when either side is empty (FR-PD-3, A-PD-2).
- `periodsOverlap(periodA, periodB) -> boolean`
- `isProbableDuplicate(a: StatementSide, b: StatementSide, settings) -> Verdict` — `StatementSide = {bankKey, accountIdentifiers?, closingBalances?, period, transactions: TxnKey[]}`; `Verdict = {isDuplicate, reason, matchedCount, countA, countB, ratio}`. Applies the same bank, same account when both sides have identifiers (A-PD-1), overlapping period, ratio at or above the threshold, and the small-statement gate: fewer than the minimum on either side requires account identifier **and** closing balance and date to match too (FR-PD-4). Symmetric in `a` and `b`. *(Amended 2026-10-04, Q1 = C)*: `Verdict` also carries `sizesComparable` (the smaller side has at least the match ratio times the larger side's transactions); it does not change whether a pair is a probable duplicate, only whether removal may be offered. `PairFinding` carries `removalAllowed`.
- `selectSnapshot(transactions: TxnKey[], matchedIndexes, limit = 10) -> SnapshotRow[]` — at most `limit`, the largest by amount, ties earlier date first, each marked (FR-PD-5, Clarification Q1 = A).
- `chooseKeptCopy(a: CopyFacts, b: CopyFacts) -> {keep, remove}` — `CopyFacts = {contentHash, manualCorrectionCount, ingestedAt}`; the one with manual corrections, else the earlier-ingested (FR-PD-11); independent of argument order.

*Database-facing:*
- `findProbableDuplicateOf(db, extracted, contentHash) -> DuplicateMatch | None` — read-only; `DuplicateMatch = {matchedStatementHash, matchedLabel, verdict, comparisonDraft}`; returns `None` when detection is off, or the hash is overridden, or the best candidate is not a duplicate.
- `recordSkippedDuplicate(db, match, driveFile, contentHash) -> ComparisonId` — writes the comparison and the remembered-file record (`probable_duplicate`); creates nothing else (FR-PD-1, FR-PD-8).
- `scanHeldStatements(db, mode: 'record'|'compute_only') -> PairFinding[]` — applies the same rule to the stored statements; `record` writes pair rows and comparisons (skipping pairs dismissed, files overridden or removed, and pairs already recorded), `compute_only` writes nothing (FR-PD-9; used by the Backfill Tool).
- `isPairScanDueNow(db) -> boolean` — true when detection is on and no scan has run, or the settings the last scan used have changed, or a re-check was requested. Cheap, so the poll cycle can ask every time.
- `runPairScan(db) -> {pairsFound}` — the poll-cycle handler: `scanHeldStatements(record)` and update scan state.

### Statement Removal Handler Component
*Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)*
- `isRemovalPendingNow(db) -> boolean` — a removal job is requested, or one has had its rows removed and is awaiting embedding cleanup.
- `processNextRemoval(db) -> RemovalResult` — `{status: 'done'|'failed'|'embeddings_pending', deletedCounts: Map<kind, count>, reason?}`; claims one job, re-verifies it (target present; manual corrections on it not above the acknowledged count), deletes in one transaction, commits, then deletes embeddings, then records the confirmed-duplicate hash and marks the pair removed (FR-PD-12/13/14).
- `deleteStatementCascade(db, statementId) -> {transactionIds, countsByTable}` — the shared dependent-row helper: the Backfill Tool's `WIPE_ORDER` applied to one statement's ids; both callers use this one implementation.

### Account Resolver Component
*Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)*
- `resolveAccount(bankName, accountIdentifier?, accountType?, currency) -> {accountId, wasCreated: boolean}` — finds the account for (bank, identifier), or creates it; with no identifier, falls back to an account keyed on the normalized bank name alone (A-2); a user-corrected type or name is never overwritten by a later extraction (exact rule: Functional Design). No external calls.
- *Scope change (2026-10-03)*: called **once per account section**; `resolveSections(sections) -> {section, accountId, wasCreated}[]` is the thin wrapper the orchestrator uses, collapsing two sections that resolve to the same account into one.

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
  - *Addendum (2026-08-17, Categorization Model Fine-Tuning feature — FR-CFT-9)*: `classify(description, amountSgd, whitelist) -> category | UNSURE` and `classifyBatch(items: {description, amountSgd}[], whitelist) -> Map<description, category|UNSURE>` — both gain an `amountSgd` parameter (the transaction's `converted_amount_sgd`), included in the prompt text alongside `description`. Callers (`categorize()`, the Ingestion Orchestrator's upfront batch step) updated to pass it through. No other signature or behavior change.

### Currency Conversion Component
- `getRate(fromCurrency, toCurrency='SGD', date) -> {rate, isApproximate, sourceDate} | RateUnavailable`
- `convert(amount, fromCurrency, date) -> ConvertedAmount | Unconverted`

### Ingestion Orchestrator Component
- `processRun(runId) -> void` — the pipeline entry point invoked when a queued run is picked up; iterates files, calls the other Worker components in sequence, updates run/file status as it goes
- `processRecategorizeJob(jobId, sourceTransactionId) -> void` — the FR-5.4 job handler, delegates to Categorization Engine
- *Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13)*: `processRun`'s per-file sequence now calls `resolveAccount` after extraction succeeds and before `recordProcessed`; no new method and no signature change. The Backfill Tool does **not** reimplement this: it creates an ordinary ingestion run record and drives it through the existing `processRun`, so the reingest follows the identical per-file path and shows up in the existing run history.
  - *Scope change (2026-10-03)*: the per-file sequence loops over the statement's account sections (resolve, record, convert with the section's currency, persist each transaction with its section link); classification stays one batch per file across all sections.
- *Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: `processRun`'s per-file sequence gains two checks and no signature changes: `lookupRememberedFile(hash)` after the exact-bytes check and before extraction, and `findProbableDuplicateOf(...)` after extraction succeeds and before the Account Resolver, calling `recordSkippedDuplicate(...)` and marking the file `skipped_probable_duplicate` on a match. The poll loop (`main.py`'s `poll_once`) gains two branches, `processNextRemoval` and `runPairScan` — see `services.md`.

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
- *Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: `deleteEmbeddings(collection: 'transactions'|'recurring_payment_names', entityIds) -> Success` — removes the points for those ids; ids that are not present are not an error (so a retried removal is safe).

### Embedding Manager Component
*Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)*
- `computeEmbedding(text) -> Vector | EmbeddingUnavailable` — calls the configured oMLX endpoint with the raw, unnormalized text (FR-9); used both by this component's own batch below and, transiently/non-persisted, by the Categorization Engine and Recurring Payment Manager at query time (see the plan doc's "Key Design Resolution")
- `processNextEmbeddingBatch() -> {processedCount}` — the poll-cycle handler (fifth `poll_once()` branch, see `services.md`): selects a bounded batch of transactions with `embedding_status = pending`, computes + persists (via Vector Store Client) each one's embedding, updates `embedding_status`; serves both newly-ingested transactions (FR-6) and the one-time historical backfill (FR-11) as the same mechanism. Stops early for the cycle on an endpoint-unavailable error rather than burning through the whole batch on doomed calls (FR-10); already-processed transactions are never revisited, and an interrupted batch simply resumes next cycle (NFR-4).

---

## Backfill Tool (new, 2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)

Command-line entry point only (Question 2 = A) — no REST endpoints, no UI, no service loop. Exact CLI argument shapes are deferred to Functional Design.

### Backfill Tool Component
- `runDryRun() -> DryRunReport` — `{statementCount, transactionCount, manualCorrectionCount, dependentRowCounts: {recategorizationJobs, recategorizationProposals, categorizationDisagreements, recurringPaymentMatches}}`; changes nothing (US-13.7).
- `createVerifiedBackup() -> {location, verified: boolean}` — refuses to proceed when `verified` is false (NFR-AB-2). Mechanism is a Functional Design decision.
- `captureManualCorrections() -> CapturedCorrection[]` — `{statementContentHash, transactionDate, amount, description, categoryId}` for every `category_source = manual` transaction (FR-AB-16).
- `wipeAndReingest(confirmation) -> ReingestSummary` — requires the explicit typed confirmation (NFR-AB-2); wipes statements, transactions, and their dependent rows; then creates an ordinary ingestion run and drives it through the Ingestion Orchestrator's existing `processRun`.
- `reapplyCorrections(captured) -> {appliedCount, unmatched: CapturedCorrection[]}` — best-effort match on content hash, date, amount, and description; every unmatched correction is returned, never dropped (FR-AB-16).
- `buildCompletionReport(...) -> CompletionReport` — unmatched corrections individually, failed PDFs with reasons, recurring-payment matches re-derived, dependent row kinds discarded, and what was preserved (FR-AB-17).

*Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)*
- `checkDuplicates() -> PairFinding[]` — new read-only command: `scanHeldStatements(compute_only)` printed with each pair's reason, comparison summary, and the copy `chooseKeptCopy` would keep; changes nothing (NFR-PD-1's evaluation; the source of the dry-run listing, FR-PD-15).
- `runDryRun()` additionally returns `duplicatePairs: {keep, skip, reason}[]` (FR-PD-15).
- `preRegisterSkips(pairs) -> RememberedFile[]` — just before the reingest, writes a `probable_duplicate` remembered-file record for each pair's copy-to-skip, pointing at the kept copy's hash and reusing the pair's comparison (FR-PD-16); recorded in the backup manifest so `restore` can undo it.
- `reapplyCorrections(captured)` additionally maps corrections captured from any file that the reingest skipped as a probable duplicate (pre-registered or flagged inline) onto the kept copy's matching transactions, via the remembered record's matched hash, before reporting any as unmatched (FR-PD-17).
- `buildCompletionReport(...)` additionally lists the skipped duplicates and the corrections carried across.

---

## Model Training (new unit, 2026-08-17, Categorization Model Fine-Tuning feature — see `categorization-model-finetuning-application-design-plan.md`)

Both components below are invoked directly as CLI entry points (`python -m ...` or equivalent) — no service loop, no polling, no job queue. Exact CLI argument shapes are deferred to Functional Design.

### Dataset Curator Component
- `curateDataset(outputDir, trainSplitRatio=0.85) -> {trainCount, valCount, sourceBreakdown: {manual, humanApprovedSimilarity}}` — FR-CFT-1..4: queries eligible transactions, builds `{description, amountSgd, categoryName, transactionId}` examples, splits, and writes both splits to `outputDir` in mlx-tune-`SFTTrainer`-ready form. Deterministic given the same DB state (NFR-CFT-4).

### Fine-Tuning Trainer Component
- `train(datasetDir, config: {loraRank, loraAlpha, learningRate, steps, ...}) -> TrainingRunResult` — FR-CFT-5/6: loads `mlx-community/gemma-4-26b-a4b-it-4bit` via mlx-tune's `FastLanguageModel`, attaches LoRA adapters per `config`, fine-tunes via `SFTTrainer` against `datasetDir`'s training split, logging configuration/metrics/artifacts to ClearML throughout.
- `evaluate(modelHandle, validationSplitPath) -> {accuracy, confusionMatrix, agreementWithLiveModel}` — FR-CFT-7: runs the fine-tuned model against the held-out validation split; separately calls the live categorization endpoint (same input shape, post-FR-CFT-9) for each validation example to compute the agreement/disagreement rate; both logged to ClearML. Called by `train()` at the end of a run, not invoked standalone.
- `saveArtifact(modelHandle, outputPath, format: 'lora_adapter'|'merged') -> ArtifactPath` — FR-CFT-8: local save only, via mlx-tune's own `save_pretrained`/`save_pretrained_merged`. No conversion, no deployment call.
  - *Addendum (2026-08-12, retroactively during Ingestion Worker Service Functional Design)*: also selects a bounded batch of `RecurringPayment` rows with `embedding_status = pending` (Database `BR-25`, added retroactively) and processes them the same way, targeting the `recurring_payment_names` collection — one unified mechanism draining both entity types' backlogs, not two separate handlers.
