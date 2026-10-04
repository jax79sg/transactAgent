# Domain Entities (DTOs) — Unit 2: API Service

Unit 2 introduces **no new persisted entities** — it reads/writes Unit 1's schema directly. This document defines the transient request/response DTO shapes for its REST API (Question 4 in Application Design plan = A, REST).

## Auth

- `LoginRequest`: `{ username: string, password: string }`
- `LoginResponse`: `{ token: string, expiresAt: datetime }`

## Transaction Management

- `TransactionFilter` (query params): `{ dateFrom?, dateTo?, bank?, category?, flowDirection?: 'in'|'out', currency?, textSearch?, categorySource?: 'similarity'|'llm'|'manual'|'unsure', page?: int, pageSize?: int, groupBy?: 'category'|'bank'|'month'|'categorySource', sortBy?, sortDir? }`
- `TransactionDTO`: `{ id, transactionDate, description, outFlow?, inFlow?, currency, bankName, category: { id, name }, categorySource, convertedAmountSgd?, conversionIsApproximate, conversionUnavailable, bankStatementId, embeddingStatus: 'pending'|'completed' }` — `embeddingStatus` added 2026-08-13 (Local Embedding-Based Semantic Similarity feature, Epic 9, AR-21), read-only
- `TransactionPage`: `{ items: TransactionDTO[], page, pageSize, totalCount, groups?: GroupSummary[] }`
- `GroupSummary`: `{ groupKey, groupLabel, subtotalOutFlowSgd, subtotalInFlowSgd, transactionCount }`
- `CategoryCorrectionRequest`: `{ categoryId: uuid }`
- `CsvExportRequest`: same shape as `TransactionFilter`, minus pagination

## Dashboard/Insights

- `DashboardFilter`: `{ dateFrom, dateTo, currency? }`
- `CategoryTrendResponse`: `{ series: [{ category, month, totalSgd }], approximateCount, excludedCount }`
- `CashFlowResponse`: `{ series: [{ month, incomeSgd, expenseSgd, netSgd }], approximateCount, excludedCount }`
- `BankBreakdownResponse`: `{ series: [{ bankName, month, totalSgd }], approximateCount, excludedCount }`
- `ConversionDisclosure` (embedded in the 3 responses above): `{ approximateCount, excludedCount, excludedTransactionIds }`

## Ingestion Trigger & Status

- `StartRunResponse`: `{ runId: uuid }` (`202 Accepted`) or `409 Conflict` with `{ existingRunId: uuid }`
- `RunStatusResponse`: `{ runId, status, startedAt, completedAt?, filesFoundCount, filesProcessedCount, filesSkippedCount, filesFailedCount }`
- `RunHistoryPage`: `{ items: RunStatusResponse[], page, pageSize, totalCount }`
- `RunFileDetail`: `{ id, driveFileName, outcome, failureReason?, transactionsExtractedCount?, processedAt }` (list, per run — `raw_extracted_text` only included on an explicit single-file detail request, not this list)

## Configuration

- `CategoryDTO`: `{ id, name, active, isReserved }`
- `AddCategoryRequest`: `{ name: string }`
- `RenameCategoryRequest`: `{ name: string }`
- `RemoveCategoryResponse` (on block): `409 Conflict` with `{ blockedByTransactionCount: int }`

## Recategorization Review (added 2026-08-02 — Epic 6)

- `ProposalDTO`: `{ id, candidateTransaction: { id, transactionDate, description, outFlow?, inFlow?, currency, bankName, currentCategory: { id, name } }, proposedCategory: { id, name }, matchScore, sourceBucket: 'unsure'|'categorized', status: 'pending'|'approved'|'rejected'|'autoApplied', createdAt, sourceTransactionId }`
- `ProposalPage`: `{ items: ProposalDTO[], page, pageSize, totalCount }`
- `PendingCountResponse`: `{ pendingCount: int }`
- `BulkProposalRequest`: `{ proposalIds: uuid[] }`
- `BulkApproveResponse`: `{ approvedIds: uuid[], failedIds: uuid[] }`
- `BulkRejectResponse`: `{ rejectedIds: uuid[], failedIds: uuid[] }`
- **Addendum (2026-08-16, Matching Precision Refinement)**:
  - `DisagreementDTO`: `{ id, candidateTransaction: TransactionDTO, similarityCategory: { id, name }, llmCategory: { id, name }, similarityScore, status: 'pending'|'resolved'|'rejected', resolvedCategory: { id, name } | null, createdAt }`
  - `DisagreementPage`: `{ items: DisagreementDTO[], page, pageSize, totalCount }`
  - `ResolveDisagreementRequest`: `{ chosenCategoryId: uuid }`
  - `PendingCountResponse` (unchanged shape) now sums proposal + disagreement pending counts (AR-26) — no new response DTO needed.

## Backup Status (added 2026-08-08 — Epic 7)

- `BackupStatusResponse`: `{ lastRunAt: datetime | null, outcome: 'success'|'failed'|null, failureCategory: 'driveConnectivity'|'other'|null, transactionCount: int | null, backupFilename: string | null }` — `outcome = null` means no backup has ever run yet (AR-14), distinct from a recorded `failed` outcome.

## Recurring Payments (added 2026-08-08 — Epic 8)

- `RecurringPaymentDTO`: `{ id, name, expectedAmount, frequency: 'monthly'|'annual', dueMonth?, dueDay, category?: { id, name }, isTrusted, status: 'dueSoon'|'overdue'|'pendingReview'|'paid', monthlySetAside? }` — `monthlySetAside` present only for `frequency = 'annual'` (AR-16); `status` computed at read time (AR-15, refined to 4 states during Code Generation — a pending match is neither `paid` nor `overdue`)
- `RecurringPaymentCreateRequest` / `RecurringPaymentUpdateRequest`: `{ name, expectedAmount, frequency, dueMonth?, dueDay, categoryId? }`
- `BulkImportRequest`: `{ rows: { name, amount, frequency, dueMonth?, dueDay }[] }`
- `BulkImportResponse`: `{ created: RecurringPaymentDTO[], failed: { row: int, reason: string }[] }` — AR-19
- `RecurringPaymentMatchDTO`: `{ id, recurringPayment: { id, name }, transaction: TransactionDTO, cyclePeriod, status: 'pending'|'approved'|'rejected'|'auto_applied', amountAtMatch, createdAt }`
- `DetectionSuggestionDTO`: `{ id, descriptionPattern, suggestedAmount, suggestedCategory?: { id, name }, occurrenceCount, status: 'new'|'dismissed'|'added' }`
- `RecurringPaymentsStatusSummaryDTO`: `{ dueSoonCount, overdueCount, pendingMatchCount, newSuggestionCount }` — backs the Dashboard section and the nav badge (US-8.3/US-8.7)

## Configurable Application Settings (added 2026-08-16)

- `SettingDTO`: `{ name, value: string, isOverridden: bool, owningServices: ('ingestion-worker'|'api-service')[], classification: 'standard'|'advanced', category: string, description: string, type: 'float'|'int'|'string'|'enum', min?: number, max?: number, allowedValues?: string[] }` — `value` is always a string on the wire (AR-28's types are metadata for client-side input rendering/validation hints, not the wire type itself, matching `SettingChange.new_value`'s string storage at the Database layer). `category`/`description` added 2026-08-16 after Build and Test user feedback that neither was originally exposed despite `.env.example` already having well-organized sections and explanatory comments for nearly every field — both now sourced directly from that same content (AR-28).
- `UpdateSettingRequest`: `{ value: string }`
- `SettingChangeResult`: `{ setting: SettingDTO, restartGuidance: RestartGuidanceDTO }` — returned by a successful `updateSetting` call
- `RestartGuidanceDTO`: `{ owningService: 'ingestion-worker'|'api-service', restartCommand: string, workerBusy?: boolean }` — `workerBusy` is present only when `owningService = 'ingestion-worker'` (AR-31); genuinely absent, not `null`, for `api-service`-owned settings (US-10.3's third edge case)
- `SettingChangeDTO`: `{ id, settingName, owningService: 'ingestion-worker'|'api-service', previousValue: string | null, newValue: string, changedAt: datetime }`
- `InvalidSettingValueError` (400): a value failing AR-28's type/range or AR-29's cross-field check
- `UnknownSettingError` (404): a name not on the AR-28 allow-list — indistinguishable whether it's a genuinely-unknown name or one of the 13 excluded secrets (NFR-CAS-2)

## Background Activity (added 2026-08-18 — Background Process Visibility)

- `ActivitySummaryDTO`: `{ current: CurrentActivityDTO | null, recent: RecentActivityEntryDTO[] }` — the sole response shape of `getActivitySummary()`
- `CurrentActivityDTO`: `{ jobType: 'ingestion_run'|'recategorization_job', startedAt: datetime }` — present only while a job is `running` (AR-35); `null` `current` in the parent means idle (FR-BPV-4)
- `RecentActivityEntryDTO`: `{ jobType: 'ingestion_run'|'recategorization_job', completedAt: datetime }` — up to 10 entries, most recent first (AR-36); an empty array means no recent activity, not an error

## Duplicate Review (added 2026-10-04 — Probable Duplicate Statement Detection, Epic 14)

*Field names are camelCase like every DTO here; enumerated values are the stored (or, for the comparison's `state`, the derived) snake_case strings, as the existing routers return an enum's `.value`.*

- `StatementLabelDTO`: `{ contentHash, fileName: string | null, bankName: string | null, periodStart: date, periodEnd: date, transactionCount: int }` — read from the stored comparison (AR-41). `fileName` is null when the file name could not be resolved at detection time; the Frontend then falls back to bank and period.
- `RemovalPreviewDTO`: `{ transactions, statementSections, recategorizationJobs, recategorizationProposals, categorizationDisagreements, recurringPaymentMatches, correctionsLost, onlyOnRemovedCopy }` — all integers (AR-41). Present only for a pending pair where removal is offered.
- `RemovalStatusDTO`: `{ jobId, status: 'queued'|'running'|'embeddings_pending'|'embeddings_failed'|'completed'|'failed', failureReason: string | null, requestedAt, finishedAt: datetime | null, deletedCounts: object | null }` — the pair's latest removal job; null when none has been requested.
- `PairDTO`: `{ id, comparisonId, status: 'pending'|'removed', removalOffered: bool, stale: bool, keep: StatementLabelDTO, remove: StatementLabelDTO, correctionsOnKept: int | null, correctionsOnRemoved: int | null, preview: RemovalPreviewDTO | null, removal: RemovalStatusDTO | null, foundAt }` — `removalOffered = false` means information only: dismiss, no remove (Question 1 = C). `stale` means a statement of the pair no longer exists; the counts are then null and removal is not offered (AR-41). `keep`/`remove` are the worker's stored proposal, never recomputed (AR-41).
- `PairPage`: `{ items: PairDTO[], page, pageSize, totalCount }`
- `PendingPairCountResponse`: `{ pendingCount: int }` — same shape as `PendingCountResponse` (AR-40).
- `RemovalRequest`: `{ removeStatementHash: string, acknowledgedCorrectionsLost: int }` — what the user saw and confirmed (AR-42).
- `ComparisonRowDTO`: `{ rank: int, transactionDate: date, description: string, outFlow: decimal | null, inFlow: decimal | null, currency: string, marker: 'also_on_other'|'only_on_this_one' }`
- `ComparisonSideDTO`: `{ label: StatementLabelDTO, rows: ComparisonRowDTO[] }` — up to 10 rows, ranked largest first.
- `ComparisonDTO`: `{ id, state: 'skipped'|'ingest_at_next_run'|'ingested_at_your_request'|'removed'|'pair_pending'|'pair_dismissed'|'pair_superseded', reason: string, matchedCount: int, matchRatio: decimal, earlier: ComparisonSideDTO, later: ComparisonSideDTO, thisFileSide: 'earlier'|'later'|null, canOverride: bool, pairId: uuid | null, removalOffered: bool | null, createdAt }` — `thisFileSide` is set only when the comparison belongs to a remembered file (AR-45); `pairId` and `removalOffered` only when it belongs to a held pair.
- `OverrideResponse`: `{ comparisonId, state: 'ingest_at_next_run'|'ingested_at_your_request', note: string | null }` — `note` says that corrections lost with a removed copy are not restored (AR-44).
- `ScanStatusDTO`: `{ lastCompletedAt: datetime | null, pairsFound: int | null, recheckRequested: bool, detectionEnabled: bool }` (AR-46).
- **Endpoint paths (fixed at Frontend Functional Design, 2026-10-04, so the two units agree)**: `GET /duplicates/pairs` (query `page`, `page_size`), `GET /duplicates/pairs/pending-count`, `GET /duplicates/comparisons/{comparisonId}`, `POST /duplicates/pairs/{pairId}/remove` (body `RemovalRequest`), `POST /duplicates/pairs/{pairId}/dismiss`, `POST /duplicates/comparisons/{comparisonId}/override`, `GET /duplicates/scan-status`, `POST /duplicates/recheck`. Remove, dismiss, and re-check return the updated pair or the scan status so the Frontend can refresh without a second call.
- **Run-file detail (addendum to `RunFileDetail`, Ingestion Trigger & Status)**: gains `duplicateComparisonId: uuid | null` and `matchedStatement: StatementLabelDTO | null`; `outcome` may now be `skipped_probable_duplicate` (the stored value, as for the other outcomes) (AR-47).
- **Settings (addendum to Configurable Application Settings)**: the catalog gains `duplicate_detection_enabled` (enumerated `false`/`true`), `duplicate_match_ratio` (decimal), `duplicate_min_transactions` (whole number), category "Duplicate Statements" (AR-48).

## Error Shape (all endpoints)

- `ErrorResponse`: `{ error: string, message: string, details?: object }` — consistent shape across all `400`/`401`/`404`/`409` responses so the Frontend has one error-handling code path.
