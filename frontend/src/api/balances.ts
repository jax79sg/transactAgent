import { apiRequest } from "./client";
import type { BalanceLookupParams, BalancesResponse, DiscrepanciesResponse, SeriesParams, SeriesResponse } from "./types";

// Epic 13 (Account Balance at a Point in Time): read-only balance views. Query names `date`, `month`, `from`, `to`
// and `granularity` are the API's own and are unchanged by the client's camelCase-to-snake_case conversion.

/** Balances at the end of one date, or of one month (the API resolves a month to its last day, or today). */
export function getBalances(params: BalanceLookupParams): Promise<BalancesResponse> {
  return apiRequest<BalancesResponse>("/balances", { query: params });
}

/** Balance over time. With no dates the API supplies the last 12 months ending today. */
export function getBalanceSeries(params: SeriesParams = {}): Promise<SeriesResponse> {
  return apiRequest<SeriesResponse>("/balances/series", { query: { ...params } });
}

export function getDiscrepancies(): Promise<DiscrepanciesResponse> {
  return apiRequest<DiscrepanciesResponse>("/balances/discrepancies");
}
