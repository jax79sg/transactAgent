/**
 * Pure round-trip functions between TransactionFilterState and a URL query string.
 * Deliberately pure (no React, no I/O) so it's a clean target for property-based
 * testing (fast-check, Partial PBT mode per requirements.md NFR-5.2) -- this is what
 * makes the transaction table's filters bookmarkable/shareable and is what dashboard
 * drill-down navigation relies on (business-logic-model.md).
 */

import type {
  CategorySourceValue,
  FlowDirection,
  GroupByOption,
  SortByOption,
  SortDir,
  TransactionFilterState,
} from "../api/types";

const STRING_KEYS = ["dateFrom", "dateTo", "bank", "category", "currency", "textSearch"] as const;
const FLOW_DIRECTIONS: FlowDirection[] = ["in", "out"];
const CATEGORY_SOURCES: CategorySourceValue[] = ["similarity", "llm", "manual", "unsure"];
const GROUP_BY_OPTIONS: GroupByOption[] = ["category", "bank", "month", "categorySource"];
const SORT_BY_OPTIONS: SortByOption[] = ["date", "amount", "category", "bank"];
const SORT_DIRS: SortDir[] = ["asc", "desc"];

export function filterStateToSearchParams(state: TransactionFilterState): URLSearchParams {
  const params = new URLSearchParams();

  for (const key of STRING_KEYS) {
    const value = state[key];
    if (value !== undefined && value !== "") params.set(key, value);
  }
  if (state.flowDirection !== undefined) params.set("flowDirection", state.flowDirection);
  if (state.categorySource !== undefined) params.set("categorySource", state.categorySource);
  if (state.groupBy !== undefined) params.set("groupBy", state.groupBy);
  if (state.sortBy !== undefined) params.set("sortBy", state.sortBy);
  if (state.sortDir !== undefined) params.set("sortDir", state.sortDir);
  if (state.page !== undefined) params.set("page", String(state.page));
  if (state.pageSize !== undefined) params.set("pageSize", String(state.pageSize));

  return params;
}

function parseEnum<T extends string>(value: string | null, allowed: T[]): T | undefined {
  return value !== null && (allowed as string[]).includes(value) ? (value as T) : undefined;
}

function parseInt10(value: string | null): number | undefined {
  if (value === null) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

export function searchParamsToFilterState(params: URLSearchParams): TransactionFilterState {
  const state: TransactionFilterState = {};

  for (const key of STRING_KEYS) {
    const value = params.get(key);
    if (value !== null && value !== "") state[key] = value;
  }
  state.flowDirection = parseEnum(params.get("flowDirection"), FLOW_DIRECTIONS);
  state.categorySource = parseEnum(params.get("categorySource"), CATEGORY_SOURCES);
  state.groupBy = parseEnum(params.get("groupBy"), GROUP_BY_OPTIONS);
  state.sortBy = parseEnum(params.get("sortBy"), SORT_BY_OPTIONS);
  state.sortDir = parseEnum(params.get("sortDir"), SORT_DIRS);
  state.page = parseInt10(params.get("page"));
  state.pageSize = parseInt10(params.get("pageSize"));

  // Strip undefined keys so the result is a "clean" object (matters for equality
  // comparisons in the round-trip property test).
  return Object.fromEntries(Object.entries(state).filter(([, v]) => v !== undefined)) as TransactionFilterState;
}
