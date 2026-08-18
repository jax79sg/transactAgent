import { apiRequest } from "./client";
import type { ActivitySummaryResponse } from "./types";

export function getActivitySummary(): Promise<ActivitySummaryResponse> {
  return apiRequest<ActivitySummaryResponse>("/background-activity/summary");
}
