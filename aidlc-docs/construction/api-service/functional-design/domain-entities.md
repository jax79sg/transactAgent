# Domain Entities (DTOs) — Unit 2: API Service

Unit 2 introduces **no new persisted entities** — it reads/writes Unit 1's schema directly. This document defines the transient request/response DTO shapes for its REST API (Question 4 in Application Design plan = A, REST).

## Auth

- `LoginRequest`: `{ username: string, password: string }`
- `LoginResponse`: `{ token: string, expiresAt: datetime }`

## Transaction Management

- `TransactionFilter` (query params): `{ dateFrom?, dateTo?, bank?, category?, flowDirection?: 'in'|'out', currency?, textSearch?, categorySource?: 'similarity'|'llm'|'manual'|'unsure', page?: int, pageSize?: int, groupBy?: 'category'|'bank'|'month'|'categorySource', sortBy?, sortDir? }`
- `TransactionDTO`: `{ id, transactionDate, description, outFlow?, inFlow?, currency, bankName, category: { id, name }, categorySource, convertedAmountSgd?, conversionIsApproximate, conversionUnavailable, bankStatementId }`
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

## Error Shape (all endpoints)

- `ErrorResponse`: `{ error: string, message: string, details?: object }` — consistent shape across all `400`/`401`/`404`/`409` responses so the Frontend has one error-handling code path.
