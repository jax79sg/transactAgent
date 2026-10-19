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
export type SortByOption = "date" | "amount" | "category" | "bank" | "description" | "converted";
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

export type RunFileOutcome = "processed" | "skipped_duplicate" | "skipped_probable_duplicate" | "failed";

export interface RunFileDetail {
  id: string;
  driveFileName: string;
  outcome: RunFileOutcome;
  failureReason: string | null;
  transactionsExtractedCount: number | null;
  processedAt: string;
  // Epic 14 (AR-47): set only for a file skipped as a probable duplicate. Optional so a run-file object built
  // without them (older fixtures) still type-checks; the API always sends them (null when not applicable).
  duplicateComparisonId?: string | null;
  matchedStatement?: StatementLabel | null;
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
  /** null means "use the frequency-based default" (issue #15). */
  dueSoonLeadDays: number | null;
}

export interface RecurringPaymentCreateRequest {
  name: string;
  expectedAmount: string;
  frequency: RecurringPaymentFrequency;
  dueMonth?: number | null;
  dueDay: number;
  categoryId?: string | null;
  dueSoonLeadDays?: number | null;
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
  /** Which cadence the detection scan matched -- null for a suggestion recorded
   * before this field existed (issue #15). */
  detectedFrequency: RecurringPaymentFrequency | null;
  suggestedDueMonth: number | null;
  suggestedDueDay: number | null;
}

export interface RecurringPaymentsStatusSummaryDTO {
  dueSoonCount: number;
  overdueCount: number;
  pendingMatchCount: number;
  newSuggestionCount: number;
}

export type SettingClassification = "standard" | "advanced";
export type SettingType = "float" | "int" | "string" | "enum";
export type SettingOwningServiceValue = "ingestion-worker" | "api-service";

export interface SettingDTO {
  name: string;
  value: string;
  isOverridden: boolean;
  owningServices: SettingOwningServiceValue[];
  classification: SettingClassification;
  category: string;
  description: string;
  type: SettingType;
  min?: number;
  max?: number;
  allowedValues?: string[];
}

export interface RestartTargetDTO {
  owningService: SettingOwningServiceValue;
  restartCommand: string;
  workerBusy?: boolean;
}

export interface SettingChangeResultDTO {
  setting: SettingDTO;
  restartGuidance: RestartTargetDTO[];
}

export interface SettingChangeDTO {
  id: string;
  settingName: string;
  owningService: SettingOwningServiceValue;
  previousValue: string | null;
  newValue: string;
  changedAt: string;
}

export type BackgroundJobType = "ingestion_run" | "recategorization_job";

export interface CurrentActivity {
  jobType: BackgroundJobType;
  startedAt: string;
}

export interface RecentActivityEntry {
  jobType: BackgroundJobType;
  completedAt: string;
}

export interface ActivitySummaryResponse {
  current: CurrentActivity | null;
  recent: RecentActivityEntry[];
}

// ---- Probable Duplicate Statement Detection (Epic 14) -- mirrors api-service's duplicates/schemas.py ----

export interface StatementLabel {
  contentHash: string;
  fileName: string | null;
  bankName: string | null;
  periodStart: string;
  periodEnd: string;
  transactionCount: number;
}

export interface RemovalPreview {
  transactions: number;
  statementSections: number;
  recategorizationJobs: number;
  recategorizationProposals: number;
  categorizationDisagreements: number;
  recurringPaymentMatches: number;
  correctionsLost: number;
  onlyOnRemovedCopy: number;
}

export type RemovalJobStatus =
  | "queued"
  | "running"
  | "embeddings_pending"
  | "embeddings_failed"
  | "completed"
  | "failed";

export interface RemovalStatus {
  jobId: string;
  status: RemovalJobStatus;
  failureReason: string | null;
  requestedAt: string;
  finishedAt: string | null;
  deletedCounts: Record<string, number> | null;
}

export type DuplicatePairStatus = "pending" | "removed" | "dismissed" | "superseded";

export interface DuplicatePair {
  id: string;
  comparisonId: string;
  status: DuplicatePairStatus;
  removalOffered: boolean;
  stale: boolean;
  keep: StatementLabel;
  remove: StatementLabel;
  correctionsOnKept: number | null;
  correctionsOnRemoved: number | null;
  preview: RemovalPreview | null;
  removal: RemovalStatus | null;
  foundAt: string;
}

export interface DuplicatePairPage {
  items: DuplicatePair[];
  page: number;
  pageSize: number;
  totalCount: number;
}

export interface PendingPairCountResponse {
  pendingCount: number;
}

export interface RemovalRequest {
  removeStatementHash: string;
  acknowledgedCorrectionsLost: number;
}

export type ComparisonMarker = "also_on_other" | "only_on_this_one";

export interface ComparisonRow {
  rank: number;
  transactionDate: string;
  description: string;
  outFlow: string | null;
  inFlow: string | null;
  currency: string;
  marker: ComparisonMarker;
}

export interface ComparisonSide {
  label: StatementLabel;
  rows: ComparisonRow[];
}

export type ComparisonState =
  | "skipped"
  | "ingest_at_next_run"
  | "ingested_at_your_request"
  | "removed"
  | "pair_pending"
  | "pair_dismissed"
  | "pair_superseded";

export interface DuplicateComparison {
  id: string;
  state: ComparisonState;
  reason: string;
  matchedCount: number;
  matchRatio: string;
  earlier: ComparisonSide;
  later: ComparisonSide;
  thisFileSide: "earlier" | "later" | null;
  canOverride: boolean;
  pairId: string | null;
  removalOffered: boolean | null;
  createdAt: string;
}

export interface OverrideResponse {
  comparisonId: string;
  state: "ingest_at_next_run" | "ingested_at_your_request";
  note: string | null;
}

export interface ScanStatus {
  lastCompletedAt: string | null;
  pairsFound: number | null;
  recheckRequested: boolean;
  detectionEnabled: boolean;
}


/** Issue #28 (Costs page) -- matches api_service/costs/schemas.py. Money is US dollars (what Google bills), sent as
 * decimal strings; never mixed with the SGD figures elsewhere in the app. */
export type CostGranularity = "day" | "week" | "month";
export type CostGroupBy = "none" | "purpose" | "model";

export interface CostFilterState {
  dateFrom: string;
  dateTo: string;
  granularity: CostGranularity;
  groupBy: CostGroupBy;
  /** The viewer's IANA time zone, so a "day" is the viewer's own calendar day. */
  timezone: string;
}

export interface CostFigures {
  costUsd: string;
  inputTokens: number;
  outputTokens: number;
  calls: number;
  /** How many of `calls` have token counts that are estimates (embeddings -- Google reports none). */
  estimatedCalls: number;
}

export interface CostPoint extends CostFigures {
  /** The day, the Monday of the week, or the first of the month (YYYY-MM-DD). */
  period: string;
  group: string;
}

export interface CostGroupTotal extends CostFigures {
  group: string;
}

export interface CostsResponse {
  currency: "USD";
  dateFrom: string;
  dateTo: string;
  granularity: CostGranularity;
  groupBy: CostGroupBy;
  timezone: string;
  /** Every period in the range, including those with no spend, so a chart has no gaps. */
  periods: string[];
  totals: CostFigures;
  series: CostPoint[];
  groups: CostGroupTotal[];
}


// ---------------------------------------------------------------------------------------------------------------------
// Epic 13: Account Balance at a Point in Time. Mirrors the DTOs the API Service builds (and its tests pin); the
// design document is construction/api-service/functional-design/domain-entities.md as corrected on 2026-10-18 (the
// series range is `start`/`end`; the statement ids in the discrepancy DTOs may be null). Every amount is the API's
// two-place decimal STRING and stays a string until it is displayed; tests/contract.test.ts checks these shapes
// against responses the real API produced (tests/fixtures/balances/), so a drift fails a test.
// ---------------------------------------------------------------------------------------------------------------------

export type AccountType = "deposit" | "credit_card" | "unknown";

export interface AnchorDTO {
  balance: string;
  asOfDate: string;
  updatedAt: string;
}

export interface AccountDTO {
  id: string;
  name: string;
  bankName: string;
  accountIdentifier: string | null;
  type: AccountType;
  /** True once the owner has chosen the type, so a later statement never overwrites it. */
  typeSetByUser: boolean;
  currency: string;
  anchor: AnchorDTO | null;
  /** True only for a deposit account. */
  canHaveAnchor: boolean;
  statementCount: number;
  transactionCount: number;
  closingBalanceCount: number;
  latestTransactionDate: string | null;
}

export interface AccountListResponse {
  items: AccountDTO[];
}

/** At least one field; the request changes exactly what it names. */
export interface AccountUpdateRequest {
  name?: string;
  type?: AccountType;
}

export interface AnchorRequest {
  balance: string;
  asOfDate: string;
}

export interface AnchorResponse {
  anchor: AnchorDTO;
  previous: AnchorDTO | null;
}

/** The surviving account is the one in the request path. */
export interface MergeRequest {
  absorbedAccountId: string;
  keepAnchorFrom?: string;
}

export type AccountBalanceStatus = "ok" | "anchor_required" | "fx_unavailable";
export type BalanceBasisSource = "anchor" | "statement_closing";
export type ExcludedReason = "anchor_required" | "fx_unavailable";

/** What a balance was worked from. */
export interface BasisDTO {
  source: BalanceBasisSource;
  date: string;
  statementId: string | null;
}

export interface AccountBalanceDTO {
  accountId: string;
  name: string;
  bankName: string;
  currency: string;
  status: AccountBalanceStatus;
  /** The account's own-currency balance: present for "ok" and "fx_unavailable" (only the conversion is missing), null for "anchor_required". */
  balanceNative: string | null;
  /** Null unless the status is "ok": a converted balance is never guessed. */
  balanceSgd: string | null;
  isApproximate: boolean;
  fxRateDate: string | null;
  basis: BasisDTO | null;
  latestTransactionDate: string | null;
}

export interface ExcludedAccountDTO {
  accountId: string;
  name: string;
  reason: ExcludedReason;
}

export interface CurrencyNetDTO {
  currency: string;
  net: string;
}

export interface UnlinkedNoticeDTO {
  count: number;
  bankNames: string[];
  earliestDate: string;
  latestDate: string;
  netByCurrency: CurrencyNetDTO[];
}

export interface BalancesResponse {
  resolvedDate: string;
  /** The date "today" is in the API's reporting time zone: the Frontend never uses its own clock after the first answer. */
  today: string;
  requestedMonth: string | null;
  ingestedThroughDate: string | null;
  accounts: AccountBalanceDTO[];
  combinedTotalSgd: string | null;
  combinedIncludesCount: number;
  excluded: ExcludedAccountDTO[];
  hasApproximate: boolean;
  unlinkedTransactions: UnlinkedNoticeDTO | null;
}

/** What is asked of GET /balances: exactly one of a date or a month. */
export type BalanceLookupParams = { date: string } | { month: string };

export type BalanceGranularity = "auto" | "day" | "month";

export interface SeriesParams {
  from?: string;
  to?: string;
  granularity?: BalanceGranularity;
}

export interface SeriesAccountDTO {
  accountId: string;
  name: string;
  currency: string;
}

export interface SeriesPointDTO {
  date: string;
  combinedSgd: string | null;
  /** SGD value per plotted account; null is a gap (no usable exchange rate that day), never zero. */
  perAccount: Record<string, string | null>;
  approximateAccountIds: string[];
}

export interface SeriesResponse {
  start: string;
  end: string;
  /** The resolved granularity, never "auto". */
  granularity: "day" | "month";
  accounts: SeriesAccountDTO[];
  missingAccounts: ExcludedAccountDTO[];
  points: SeriesPointDTO[];
}

export interface StatementDifferenceDTO {
  statementId: string | null;
  closingDate: string;
  printedBalance: string;
  computedBalance: string;
  /** Printed minus computed from the anchor alone. */
  difference: string;
}

export interface PeriodGapDTO {
  fromStatementId: string | null;
  toStatementId: string | null;
  fromDate: string;
  toDate: string;
  printedChange: string;
  transactionNet: string;
  /** Printed change minus the net of the transactions between the two closing dates. */
  gap: string;
}

export interface AccountDiscrepancyDTO {
  accountId: string;
  name: string;
  currency: string;
  statementsChecked: number;
  periodsChecked: number;
  statementDifferences: StatementDifferenceDTO[];
  periodGaps: PeriodGapDTO[];
}

export interface DiscrepanciesResponse {
  tolerance: string;
  accountsChecked: number;
  items: AccountDiscrepancyDTO[];
}
