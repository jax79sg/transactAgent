// Builders for the probable-duplicate tests (Epic 14): the UOB June pair is the running example.
import type {
  ComparisonRow,
  ComparisonSide,
  DuplicateComparison,
  DuplicatePair,
  RemovalPreview,
  ScanStatus,
  StatementLabel,
} from "../src/api/types";

export function label(overrides: Partial<StatementLabel> = {}): StatementLabel {
  return {
    contentHash: "a".repeat(64),
    fileName: "JUN 2026_0728.pdf",
    bankName: "UOB",
    periodStart: "2026-06-02",
    periodEnd: "2026-06-30",
    transactionCount: 5,
    ...overrides,
  };
}

export function preview(overrides: Partial<RemovalPreview> = {}): RemovalPreview {
  return {
    transactions: 5,
    statementSections: 0,
    recategorizationJobs: 0,
    recategorizationProposals: 0,
    categorizationDisagreements: 0,
    recurringPaymentMatches: 0,
    correctionsLost: 0,
    onlyOnRemovedCopy: 0,
    ...overrides,
  };
}

export function pair(overrides: Partial<DuplicatePair> = {}): DuplicatePair {
  return {
    id: "pair-1",
    comparisonId: "cmp-1",
    status: "pending",
    removalOffered: true,
    stale: false,
    keep: label({ contentHash: "a".repeat(64), fileName: "JUN 2026_0728.pdf" }),
    remove: label({ contentHash: "b".repeat(64), fileName: "JUN 2026_0828.pdf" }),
    correctionsOnKept: 2,
    correctionsOnRemoved: 0,
    preview: preview(),
    removal: null,
    foundAt: "2026-10-03T10:00:00Z",
    ...overrides,
  };
}

export function scan(overrides: Partial<ScanStatus> = {}): ScanStatus {
  return { lastCompletedAt: "2026-10-04T12:00:00Z", pairsFound: 1, recheckRequested: false, detectionEnabled: true, ...overrides };
}

export function row(rank: number, overrides: Partial<ComparisonRow> = {}): ComparisonRow {
  return {
    rank,
    transactionDate: "2026-06-05",
    description: `MERCHANT ${rank}`,
    outFlow: `${100 - rank}.00`,
    inFlow: null,
    currency: "SGD",
    marker: "also_on_other",
    ...overrides,
  };
}

export function side(overrides: Partial<ComparisonSide> = {}): ComparisonSide {
  return { label: label(), rows: [row(1), row(2, { marker: "only_on_this_one" })], ...overrides };
}

export function comparison(overrides: Partial<DuplicateComparison> = {}): DuplicateComparison {
  return {
    id: "cmp-1",
    state: "skipped",
    reason: "5 of 5 transactions match (the smaller statement); same bank; overlapping period 2 Jun to 30 Jun 2026.",
    matchedCount: 5,
    matchRatio: "1.0000",
    earlier: side({ label: label({ fileName: "JUN 2026_0728.pdf" }) }),
    later: side({ label: label({ contentHash: "b".repeat(64), fileName: "JUN 2026_0828.pdf" }) }),
    thisFileSide: "later",
    canOverride: true,
    pairId: null,
    removalOffered: null,
    createdAt: "2026-10-03T10:00:00Z",
    ...overrides,
  };
}
