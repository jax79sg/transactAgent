// Epic 13: responses the REAL API produced (api-service/tests/test_contract_fixtures.py writes and guards the files),
// loaded as typed values for the Frontend's tests. tests/contract.test.ts checks their shapes against the DTO types,
// so a test that builds on these builds on what the API really returns, not on a hand-typed guess.

import accountsListJson from "./fixtures/balances/accounts-list.json";
import anchorCreatedJson from "./fixtures/balances/anchor-created.json";
import anchorReplacedJson from "./fixtures/balances/anchor-replaced.json";
import balancesDateJson from "./fixtures/balances/balances-date.json";
import balancesMonthJson from "./fixtures/balances/balances-month.json";
import discrepanciesJson from "./fixtures/balances/discrepancies.json";
import mergeSuccessJson from "./fixtures/balances/merge-success.json";
import seriesDayJson from "./fixtures/balances/series-day.json";
import seriesMonthJson from "./fixtures/balances/series-month.json";
import type {
  AccountDTO,
  AccountListResponse,
  AnchorResponse,
  BalancesResponse,
  DiscrepanciesResponse,
  SeriesResponse,
} from "../src/api/types";

/** A deep copy, so one test changing a fixture cannot leak into the next. */
function clone<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export const accountsListFixture = (): AccountListResponse => clone(accountsListJson);
export const anchorCreatedFixture = (): AnchorResponse => clone(anchorCreatedJson);
export const anchorReplacedFixture = (): AnchorResponse => clone(anchorReplacedJson);
export const balancesDateFixture = (): BalancesResponse => clone(balancesDateJson);
export const balancesMonthFixture = (): BalancesResponse => clone(balancesMonthJson);
export const discrepanciesFixture = (): DiscrepanciesResponse => clone(discrepanciesJson);
export const mergeSuccessFixture = (): AccountDTO => clone(mergeSuccessJson);
export const seriesDayFixture = (): SeriesResponse => clone(seriesDayJson);
export const seriesMonthFixture = (): SeriesResponse => clone(seriesMonthJson);

/** The account ids the contract scenario fixes (UUID(int=n)), for tests that look an account up by role. */
export const FIXTURE_ACCOUNT_IDS = {
  main: "00000000-0000-0000-0000-000000000001",
  usd: "00000000-0000-0000-0000-000000000002",
  eur: "00000000-0000-0000-0000-000000000003",
  fresh: "00000000-0000-0000-0000-000000000004",
  card: "00000000-0000-0000-0000-000000000005",
} as const;

/** An account from the real fixture by role, with any field overridden (a copy, safe to change). */
export function fixtureAccount(role: keyof typeof FIXTURE_ACCOUNT_IDS, overrides: Partial<AccountDTO> = {}): AccountDTO {
  const found = accountsListFixture().items.find((account) => account.id === FIXTURE_ACCOUNT_IDS[role]);
  if (!found) throw new Error(`no ${role} account in the accounts-list fixture`);
  return { ...found, ...overrides };
}
