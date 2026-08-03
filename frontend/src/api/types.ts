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

export type IngestionRunStatus = "queued" | "running" | "completed" | "completed_with_failures" | "failed";

export interface RunStatusResponse {
  runId: string;
  status: IngestionRunStatus;
  startedAt: string;
  completedAt: string | null;
  filesFoundCount: number;
  filesProcessedCount: number;
  filesSkippedCount: number;
  filesFailedCount: number;
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
