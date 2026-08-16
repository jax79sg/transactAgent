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

- `SettingDTO`: `{ name, value: string, owningService: 'ingestion-worker'|'api-service', classification: 'standard'|'advanced', type: 'float'|'int'|'string'|'enum', min?: number, max?: number, allowedValues?: string[] }` — `value` is always a string on the wire (AR-28's types are metadata for client-side input rendering/validation hints, not the wire type itself, matching `SettingChange.new_value`'s string storage at the Database layer)
- `UpdateSettingRequest`: `{ value: string }`
- `SettingChangeResult`: `{ setting: SettingDTO, restartGuidance: RestartGuidanceDTO }` — returned by a successful `updateSetting` call
- `RestartGuidanceDTO`: `{ owningService: 'ingestion-worker'|'api-service', restartCommand: string, workerBusy?: boolean }` — `workerBusy` is present only when `owningService = 'ingestion-worker'` (AR-31); genuinely absent, not `null`, for `api-service`-owned settings (US-10.3's third edge case)
- `SettingChangeDTO`: `{ id, settingName, owningService: 'ingestion-worker'|'api-service', previousValue: string | null, newValue: string, changedAt: datetime }`
- `InvalidSettingValueError` (400): a value failing AR-28's type/range or AR-29's cross-field check
- `UnknownSettingError` (404): a name not on the AR-28 allow-list — indistinguishable whether it's a genuinely-unknown name or one of the 13 excluded secrets (NFR-CAS-2)

## Error Shape (all endpoints)

- `ErrorResponse`: `{ error: string, message: string, details?: object }` — consistent shape across all `400`/`401`/`404`/`409` responses so the Frontend has one error-handling code path.
