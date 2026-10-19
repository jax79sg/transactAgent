import { describe, expect, it } from "vitest";

import accountsListJson from "./fixtures/balances/accounts-list.json";
import anchorCreatedJson from "./fixtures/balances/anchor-created.json";
import anchorReplacedJson from "./fixtures/balances/anchor-replaced.json";
import balancesDateJson from "./fixtures/balances/balances-date.json";
import balancesMonthJson from "./fixtures/balances/balances-month.json";
import discrepanciesJson from "./fixtures/balances/discrepancies.json";
import errorMergeJson from "./fixtures/balances/error-merge-appear-together.json";
import error422Json from "./fixtures/balances/error-422-date.json";
import mergeSuccessJson from "./fixtures/balances/merge-success.json";
import seriesDayJson from "./fixtures/balances/series-day.json";
import seriesMonthJson from "./fixtures/balances/series-month.json";
import type {
  AccountBalanceDTO,
  AccountBalanceStatus,
  AccountDiscrepancyDTO,
  AccountDTO,
  AccountType,
  AnchorDTO,
  AnchorResponse,
  ApiErrorBody,
  BalanceBasisSource,
  BalancesResponse,
  BasisDTO,
  CurrencyNetDTO,
  DiscrepanciesResponse,
  ExcludedAccountDTO,
  ExcludedReason,
  PeriodGapDTO,
  SeriesAccountDTO,
  SeriesPointDTO,
  SeriesResponse,
  StatementDifferenceDTO,
  UnlinkedNoticeDTO,
} from "../src/api/types";

// Epic 13 contract guard, Frontend side. The fixtures are responses the REAL API produced
// (api-service/tests/test_contract_fixtures.py writes them and fails when the API stops matching them). Here each
// response's keys, at every level, must equal the keys of the TypeScript type. The key maps are Records over
// `keyof Type`, so adding or removing a field in types.ts without updating the map is a compile error, and a
// fixture with other keys is a failing test. This is what would have caught `start`/`end` versus `from`/`to`.

const ANCHOR: Record<keyof AnchorDTO, true> = { balance: true, asOfDate: true, updatedAt: true };

const ACCOUNT: Record<keyof AccountDTO, true> = {
  id: true,
  name: true,
  bankName: true,
  accountIdentifier: true,
  type: true,
  typeSetByUser: true,
  currency: true,
  anchor: true,
  canHaveAnchor: true,
  statementCount: true,
  transactionCount: true,
  closingBalanceCount: true,
  latestTransactionDate: true,
};

const BASIS: Record<keyof BasisDTO, true> = { source: true, date: true, statementId: true };

const ACCOUNT_BALANCE: Record<keyof AccountBalanceDTO, true> = {
  accountId: true,
  name: true,
  bankName: true,
  currency: true,
  status: true,
  balanceNative: true,
  balanceSgd: true,
  isApproximate: true,
  fxRateDate: true,
  basis: true,
  latestTransactionDate: true,
};

const EXCLUDED: Record<keyof ExcludedAccountDTO, true> = { accountId: true, name: true, reason: true };
const CURRENCY_NET: Record<keyof CurrencyNetDTO, true> = { currency: true, net: true };

const UNLINKED: Record<keyof UnlinkedNoticeDTO, true> = {
  count: true,
  bankNames: true,
  earliestDate: true,
  latestDate: true,
  netByCurrency: true,
};

const BALANCES: Record<keyof BalancesResponse, true> = {
  resolvedDate: true,
  today: true,
  requestedMonth: true,
  ingestedThroughDate: true,
  accounts: true,
  combinedTotalSgd: true,
  combinedIncludesCount: true,
  excluded: true,
  hasApproximate: true,
  unlinkedTransactions: true,
};

const SERIES_ACCOUNT: Record<keyof SeriesAccountDTO, true> = { accountId: true, name: true, currency: true };
const SERIES_POINT: Record<keyof SeriesPointDTO, true> = {
  date: true,
  combinedSgd: true,
  perAccount: true,
  approximateAccountIds: true,
};
const SERIES: Record<keyof SeriesResponse, true> = {
  start: true,
  end: true,
  granularity: true,
  accounts: true,
  missingAccounts: true,
  points: true,
};

const STATEMENT_DIFFERENCE: Record<keyof StatementDifferenceDTO, true> = {
  statementId: true,
  closingDate: true,
  printedBalance: true,
  computedBalance: true,
  difference: true,
};
const PERIOD_GAP: Record<keyof PeriodGapDTO, true> = {
  fromStatementId: true,
  toStatementId: true,
  fromDate: true,
  toDate: true,
  printedChange: true,
  transactionNet: true,
  gap: true,
};
const ACCOUNT_DISCREPANCY: Record<keyof AccountDiscrepancyDTO, true> = {
  accountId: true,
  name: true,
  currency: true,
  statementsChecked: true,
  periodsChecked: true,
  statementDifferences: true,
  periodGaps: true,
};
const DISCREPANCIES: Record<keyof DiscrepanciesResponse, true> = {
  tolerance: true,
  accountsChecked: true,
  items: true,
};
const ANCHOR_RESPONSE: Record<keyof AnchorResponse, true> = { anchor: true, previous: true };
const API_ERROR: Record<keyof ApiErrorBody, true> = { error: true, message: true, details: true };

const ACCOUNT_TYPES: Record<AccountType, true> = { deposit: true, credit_card: true, unknown: true };
const STATUSES: Record<AccountBalanceStatus, true> = { ok: true, anchor_required: true, fx_unavailable: true };
const BASIS_SOURCES: Record<BalanceBasisSource, true> = { anchor: true, statement_closing: true };
const EXCLUDED_REASONS: Record<ExcludedReason, true> = { anchor_required: true, fx_unavailable: true };
const RESOLVED_GRANULARITIES: Record<SeriesResponse["granularity"], true> = { day: true, month: true };

function expectShape<T>(value: unknown, map: Record<keyof T, true>, where: string): void {
  expect(value, where).toBeTypeOf("object");
  expect(value, where).not.toBeNull();
  expect(Object.keys(value as object).sort(), where).toEqual(Object.keys(map).sort());
}

function expectIn(value: unknown, allowed: Record<string, true>, where: string): void {
  expect(Object.keys(allowed), where).toContain(value);
}

function asArray(value: unknown, where: string): unknown[] {
  expect(Array.isArray(value), where).toBe(true);
  return value as unknown[];
}

type Json = Record<string, unknown>;

function expectBalances(response: unknown, where: string): void {
  expectShape<BalancesResponse>(response, BALANCES, where);
  const body = response as Json;
  for (const account of asArray(body.accounts, `${where}.accounts`) as Json[]) {
    expectShape<AccountBalanceDTO>(account, ACCOUNT_BALANCE, `${where}.accounts[]`);
    expectIn(account.status, STATUSES, `${where} status`);
    if (account.basis !== null) {
      expectShape<BasisDTO>(account.basis, BASIS, `${where}.basis`);
      expectIn((account.basis as Json).source, BASIS_SOURCES, `${where} basis.source`);
    }
  }
  for (const excluded of asArray(body.excluded, `${where}.excluded`)) {
    expectShape<ExcludedAccountDTO>(excluded, EXCLUDED, `${where}.excluded[]`);
    expectIn((excluded as Json).reason, EXCLUDED_REASONS, `${where} excluded.reason`);
  }
  if (body.unlinkedTransactions !== null) {
    expectShape<UnlinkedNoticeDTO>(body.unlinkedTransactions, UNLINKED, `${where}.unlinkedTransactions`);
    for (const net of asArray((body.unlinkedTransactions as Json).netByCurrency, "netByCurrency")) {
      expectShape<CurrencyNetDTO>(net, CURRENCY_NET, `${where}.netByCurrency[]`);
    }
  }
}

function expectSeries(response: unknown, where: string): void {
  expectShape<SeriesResponse>(response, SERIES, where);
  const body = response as Json;
  expectIn(body.granularity, RESOLVED_GRANULARITIES, `${where}.granularity`);
  const plottedIds = new Set<string>();
  for (const account of asArray(body.accounts, `${where}.accounts`) as Json[]) {
    expectShape<SeriesAccountDTO>(account, SERIES_ACCOUNT, `${where}.accounts[]`);
    plottedIds.add(account.accountId as string);
  }
  for (const missing of asArray(body.missingAccounts, `${where}.missingAccounts`)) {
    expectShape<ExcludedAccountDTO>(missing, EXCLUDED, `${where}.missingAccounts[]`);
  }
  for (const point of asArray(body.points, `${where}.points`) as Json[]) {
    expectShape<SeriesPointDTO>(point, SERIES_POINT, `${where}.points[]`);
    expect(new Set(Object.keys(point.perAccount as object)), `${where} perAccount ids`).toEqual(plottedIds);
  }
}

describe("API contract: Epic 13 fixtures from the real API match the Frontend's types", () => {
  it("the account list", () => {
    expect(Object.keys(accountsListJson)).toEqual(["items"]);
    for (const account of accountsListJson.items as unknown as Json[]) {
      expectShape<AccountDTO>(account, ACCOUNT, "accounts-list.items[]");
      expectIn(account.type, ACCOUNT_TYPES, "account type");
      if (account.anchor !== null) expectShape<AnchorDTO>(account.anchor, ANCHOR, "accounts-list anchor");
    }
  });

  it("a lookup by date and a lookup by month", () => {
    expectBalances(balancesDateJson, "balances-date");
    expectBalances(balancesMonthJson, "balances-month");
  });

  it("a daily series and a month-end series, whose range is start/end and never from/to", () => {
    expectSeries(seriesDayJson, "series-day");
    expectSeries(seriesMonthJson, "series-month");
    for (const body of [seriesDayJson, seriesMonthJson]) {
      expect(body).not.toHaveProperty("from");
      expect(body).not.toHaveProperty("to");
    }
  });

  it("the discrepancies, with their statement ids", () => {
    expectShape<DiscrepanciesResponse>(discrepanciesJson, DISCREPANCIES, "discrepancies");
    for (const item of discrepanciesJson.items as unknown as Json[]) {
      expectShape<AccountDiscrepancyDTO>(item, ACCOUNT_DISCREPANCY, "discrepancies.items[]");
      for (const difference of asArray(item.statementDifferences, "statementDifferences")) {
        expectShape<StatementDifferenceDTO>(difference, STATEMENT_DIFFERENCE, "statementDifferences[]");
      }
      for (const gap of asArray(item.periodGaps, "periodGaps")) expectShape<PeriodGapDTO>(gap, PERIOD_GAP, "periodGaps[]");
    }
  });

  it("setting and replacing an anchor, and the merged account", () => {
    expectShape<AnchorResponse>(anchorCreatedJson, ANCHOR_RESPONSE, "anchor-created");
    expectShape<AnchorResponse>(anchorReplacedJson, ANCHOR_RESPONSE, "anchor-replaced");
    expect(anchorCreatedJson.previous).toBeNull();
    expectShape<AnchorDTO>(anchorReplacedJson.previous, ANCHOR, "anchor-replaced.previous");
    expectShape<AccountDTO>(mergeSuccessJson, ACCOUNT, "merge-success");
  });

  it("the API's error body and the framework's own 422 body", () => {
    expectShape<ApiErrorBody>(errorMergeJson, API_ERROR, "error-merge-appear-together");
    expect(errorMergeJson.error).toBe("merge_appear_together");
    // A malformed date never reaches the API's own error shape: FastAPI answers {detail: [...]}, which has no
    // `message`, so the screen words a 422 itself.
    expect(Object.keys(error422Json)).toEqual(["detail"]);
    for (const problem of error422Json.detail as unknown as Json[]) {
      expect(Object.keys(problem)).toEqual(expect.arrayContaining(["loc", "msg", "type"]));
    }
  });
});

describe("API contract: the values the Frontend relies on", () => {
  const MONEY_FIELDS = new Set([
    "balance",
    "balanceNative",
    "balanceSgd",
    "combinedTotalSgd",
    "combinedSgd",
    "net",
    "tolerance",
    "printedBalance",
    "computedBalance",
    "difference",
    "printedChange",
    "transactionNet",
    "gap",
  ]);
  const TWO_PLACES = /^-?\d+\.\d{2}$/;
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
  const DATE_FIELDS = new Set([
    "asOfDate",
    "latestTransactionDate",
    "resolvedDate",
    "today",
    "ingestedThroughDate",
    "fxRateDate",
    "earliestDate",
    "latestDate",
    "closingDate",
    "fromDate",
    "toDate",
    "start",
    "end",
    "date",
  ]);
  const all: [string, unknown][] = [
    ["accounts-list", accountsListJson],
    ["anchor-created", anchorCreatedJson],
    ["anchor-replaced", anchorReplacedJson],
    ["balances-date", balancesDateJson],
    ["balances-month", balancesMonthJson],
    ["discrepancies", discrepanciesJson],
    ["merge-success", mergeSuccessJson],
    ["series-day", seriesDayJson],
    ["series-month", seriesMonthJson],
  ];

  function walk(where: string, value: unknown, visit: (field: string, v: unknown, at: string) => void): void {
    if (Array.isArray(value)) {
      value.forEach((item, i) => walk(`${where}[${i}]`, item, visit));
    } else if (value !== null && typeof value === "object") {
      for (const [field, inner] of Object.entries(value)) {
        if (field === "perAccount") {
          for (const [id, amount] of Object.entries(inner as object)) visit("perAccount", amount, `${where}.perAccount.${id}`);
        } else {
          visit(field, inner, `${where}.${field}`);
          walk(`${where}.${field}`, inner, visit);
        }
      }
    }
  }

  it("every amount is an exact two-place decimal string, or null", () => {
    let seen = 0;
    for (const [name, fixture] of all) {
      walk(name, fixture, (field, v, at) => {
        if (field !== "perAccount" && !MONEY_FIELDS.has(field)) return;
        seen += 1;
        if (v !== null) {
          expect(typeof v, at).toBe("string");
          expect(v as string, at).toMatch(TWO_PLACES);
        }
      });
    }
    expect(seen).toBeGreaterThan(40); // the walk really did visit amounts
  });

  it("every date is a plain YYYY-MM-DD string, or null", () => {
    let seen = 0;
    for (const [name, fixture] of all) {
      walk(name, fixture, (field, v, at) => {
        if (!DATE_FIELDS.has(field)) return;
        seen += 1;
        if (v !== null) expect(v as string, at).toMatch(ISO_DAY);
      });
    }
    expect(seen).toBeGreaterThan(40);
  });

  it("the fixtures between them show every status, both bases, a gap, an approximate figure and a two-currency notice", () => {
    const accounts = [...balancesDateJson.accounts, ...balancesMonthJson.accounts] as unknown as AccountBalanceDTO[];
    expect(new Set(accounts.map((a) => a.status))).toEqual(new Set(Object.keys(STATUSES)));
    expect(new Set(accounts.map((a) => a.basis?.source).filter(Boolean))).toEqual(new Set(Object.keys(BASIS_SOURCES)));
    expect(accounts.some((a) => a.isApproximate)).toBe(true);
    expect(balancesDateJson.unlinkedTransactions?.netByCurrency.length).toBeGreaterThan(1);
    const dayPoints = seriesDayJson.points as unknown as { perAccount: Record<string, string | null>; approximateAccountIds: string[] }[];
    expect(dayPoints.some((p) => Object.values(p.perAccount).includes(null))).toBe(true);
    expect(dayPoints.some((p) => p.approximateAccountIds.length > 0)).toBe(true);
    expect(discrepanciesJson.items[0].statementDifferences.length).toBeGreaterThan(0);
    expect(discrepanciesJson.items[0].periodGaps.length).toBeGreaterThan(0);
  });
});
