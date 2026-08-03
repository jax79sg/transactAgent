import { apiRequest } from "./client";
import type { BankBreakdownResponse, CashFlowResponse, CategoryTrendResponse, DashboardFilterState } from "./types";

// A plain interface (no index signature) isn't structurally assignable to
// Record<string, unknown> even when every property is compatible -- an explicit
// spread satisfies the compiler without weakening DashboardFilterState's own shape.
function asQuery(filter: DashboardFilterState): Record<string, unknown> {
  return { ...filter };
}

export function getCategoryTrends(filter: DashboardFilterState): Promise<CategoryTrendResponse> {
  return apiRequest<CategoryTrendResponse>("/dashboards/category-trends", { query: asQuery(filter) });
}

export function getCashFlow(filter: DashboardFilterState): Promise<CashFlowResponse> {
  return apiRequest<CashFlowResponse>("/dashboards/cash-flow", { query: asQuery(filter) });
}

export function getBankBreakdown(filter: DashboardFilterState): Promise<BankBreakdownResponse> {
  return apiRequest<BankBreakdownResponse>("/dashboards/bank-breakdown", { query: asQuery(filter) });
}
