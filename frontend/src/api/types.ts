/** DTO shapes matching api-service/functional-design/domain-entities.md (camelCase,
 * per Unit 2's CamelModel serialization). */

export interface LoginResponse {
  token: string;
  expiresAt: string;
}

export interface CategoryRef {
  id: string;
  name: string;
}

export type CategorySourceValue = "similarity" | "llm" | "manual" | "unsure";
export type FlowDirection = "in" | "out";
export type GroupByOption = "category" | "bank" | "month" | "categorySource";
export type SortByOption = "date" | "amount" | "category" | "bank";
export type SortDir = "asc" | "desc";

export interface TransactionDTO {
  id: string;
  transactionDate: string;
  description: string;
  outFlow: string | null;
  inFlow: string | null;
  currency: string;
  bankName: string;
  category: CategoryRef;
  categorySource: CategorySourceValue;
  convertedAmountSgd: string | null;
  conversionIsApproximate: boolean;
  conversionUnavailable: boolean;
  bankStatementId: string;
  /** Epic 9 (Local Embedding-Based Semantic Similarity): processing-status only --
   * does NOT indicate a precedent/match was found, just that the embedding step
   * has run for this transaction (FR-7). */
  embeddingStatus: "pending" | "completed";
}

export interface GroupSummary {
  groupKey: string;
  groupLabel: string;
  subtotalOutFlowSgd: string;
  subtotalInFlowSgd: string;
  transactionCount: number;
}

export interface TransactionPage {
  items: TransactionDTO[];
  page: number;
  pageSize: number;
  totalCount: number;
  groups: GroupSummary[] | null;
}

export interface TransactionFilterState {
  dateFrom?: string;
  dateTo?: string;
  bank?: string;
  category?: string;
  flowDirection?: FlowDirection;
  currency?: string;
  textSearch?: string;
  categorySource?: CategorySourceValue;
  groupBy?: GroupByOption;
  sortBy?: SortByOption;
  sortDir?: SortDir;
  page?: number;
  pageSize?: number;
}

export interface TransactionUpdatedResponse {
  transaction: TransactionDTO;
  recategorizationJobId: string;
}

export interface ConversionDisclosure {
  approximateCount: number;
  excludedCount: number;
  excludedTransactionIds: string[];
}

export interface CategoryTrendPoint {
  category: string;
  month: string;
  totalSgd: string;
}

export interface CategoryTrendResponse {
  series: CategoryTrendPoint[];
  disclosure: ConversionDisclosure;
}

export interface CashFlowPoint {
  month: string;
  incomeSgd: string;
  expenseSgd: string;
  netSgd: string;
}

export interface CashFlowResponse {
  series: CashFlowPoint[];
  disclosure: ConversionDisclosure;
}

export interface BankBreakdownPoint {
  bankName: string;
  month: string;
  totalSgd: string;
}

export interface BankBreakdownResponse {
  series: BankBreakdownPoint[];
  disclosure: ConversionDisclosure;
}

export interface DashboardFilterState {
  dateFrom: string;
  dateTo: string;
  currency?: string;
}

export interface AskAiRequest {
  question: string;
  dateFrom?: string;
  dateTo?: string;
  useAllTransactions?: boolean;
}

export interface AskAiResponse {
  answer: string;
  transactionsConsidered: number;
  truncated: boolean;
}

export type IngestionRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_failures"
  | "failed"
  | "cancelled";

export interface RunStatusResponse {
  runId: string;
  status: IngestionRunStatus;
  startedAt: string;
  completedAt: string | null;
  filesFoundCount: number;
  filesProcessedCount: number;
  filesSkippedCount: number;
  filesFailedCount: number;
  cancelRequestedAt: string | null;
}

export interface RunHistoryPage {
  items: RunStatusResponse[];
  page: number;
  pageSize: number;
  totalCount: number;
}

export type RunFileOutcome = "processed" | "skipped_duplicate" | "failed";

export interface RunFileDetail {
  id: string;
  driveFileName: string;
  outcome: RunFileOutcome;
  failureReason: string | null;
  transactionsExtractedCount: number | null;
  processedAt: string;
}

export interface RunLogLine {
  id: number;
  loggedAt: string;
  level: string;
  loggerName: string;
  message: string;
}

export interface CategoryDTO {
  id: string;
  name: string;
  active: boolean;
  isReserved: boolean;
  transactionCount: number;
}

export interface ApiErrorBody {
  error: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface DriveConnectionStatus {
  connected: boolean;
}

export interface DriveAuthorizationUrl {
  authorizationUrl: string;
}

export type ProposalSourceBucket = "unsure" | "categorized";
export type ProposalStatus = "pending" | "approved" | "rejected" | "auto_applied";

export interface ProposalDTO {
  id: string;
  candidateTransaction: TransactionDTO;
  proposedCategory: CategoryRef;
  matchScore: string;
  sourceBucket: ProposalSourceBucket;
  status: ProposalStatus;
  createdAt: string;
  sourceTransactionId: string;
}

export interface ProposalPage {
  items: ProposalDTO[];
  page: number;
  pageSize: number;
  totalCount: number;
}

export interface PendingCountResponse {
  pendingCount: number;
}

export interface BulkApproveResponse {
  approvedIds: string[];
  failedIds: string[];
}

export interface BulkRejectResponse {
  rejectedIds: string[];
  failedIds: string[];
}

/** Matching Precision Refinement: a genuine categorization disagreement (both
 * similarity matching and the always-on LLM confident, but differing) -- a
 * distinct entity from ProposalDTO above, with two candidate categories instead
 * of one. */
export type DisagreementStatus = "pending" | "resolved" | "rejected";

export interface DisagreementDTO {
  id: string;
  candidateTransaction: TransactionDTO;
  similarityCategory: CategoryRef;
  llmCategory: CategoryRef;
  similarityScore: string;
  status: DisagreementStatus;
  resolvedCategory: CategoryRef | null;
  createdAt: string;
}

export interface DisagreementPage {
  items: DisagreementDTO[];
  page: number;
  pageSize: number;
  totalCount: number;
}

export type BackupOutcome = "success" | "failed" | null;
export type BackupFailureCategory = "drive_connectivity" | "other" | null;

export interface BackupStatusResponse {
  lastRunAt: string | null;
  outcome: BackupOutcome;
  failureCategory: BackupFailureCategory;
  transactionCount: number | null;
  backupFilename: string | null;
}

export type RecurringPaymentFrequency = "monthly" | "annual";
export type RecurringPaymentStatus = "due_soon" | "overdue" | "pending_review" | "paid";

export interface RecurringPaymentDTO {
  id: string;
  name: string;
  expectedAmount: string;
  frequency: RecurringPaymentFrequency;
  dueMonth: number | null;
  dueDay: number;
  category: CategoryRef | null;
  isTrusted: boolean;
  status: RecurringPaymentStatus;
  monthlySetAside: string | null;
}

export interface RecurringPaymentCreateRequest {
  name: string;
  expectedAmount: string;
  frequency: RecurringPaymentFrequency;
  dueMonth?: number | null;
  dueDay: number;
  categoryId?: string | null;
}

export type RecurringPaymentUpdateRequest = RecurringPaymentCreateRequest;

export interface BulkImportRow {
  name: string;
  amount: string;
  frequency: RecurringPaymentFrequency;
  dueMonth?: string | null;
  dueDay: string;
}

export interface BulkImportRowFailure {
  row: number;
  reason: string;
}

export interface BulkImportResponse {
  created: RecurringPaymentDTO[];
  failed: BulkImportRowFailure[];
}

export interface RecurringPaymentRef {
  id: string;
  name: string;
}

export interface RecurringPaymentMatchDTO {
  id: string;
  recurringPayment: RecurringPaymentRef;
  transaction: TransactionDTO;
  cyclePeriod: string;
  status: "pending" | "approved" | "rejected" | "auto_applied";
  amountAtMatch: string;
  createdAt: string;
}

export interface DetectionSuggestionDTO {
  id: string;
  descriptionPattern: string;
  suggestedAmount: string;
  suggestedCategory: CategoryRef | null;
  occurrenceCount: number;
  status: "new" | "dismissed" | "added";
}

export interface RecurringPaymentsStatusSummaryDTO {
  dueSoonCount: number;
  overdueCount: number;
  pendingMatchCount: number;
  newSuggestionCount: number;
}
