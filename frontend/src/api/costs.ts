import { apiRequest } from "./client";
import type { CostFilterState, CostsResponse } from "./types";

export function getCosts(filter: CostFilterState): Promise<CostsResponse> {
  return apiRequest<CostsResponse>("/costs", { query: { ...filter } });
}
