import { apiRequest } from "./client";
import type { RunFileDetail, RunHistoryPage, RunLogLine, RunStatusResponse } from "./types";
import { ApiError } from "./client";

export async function startRun(): Promise<{ runId: string }> {
  try {
    return await apiRequest<{ runId: string }>("/ingestion/runs", { method: "POST" });
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const existingRunId = err.body.details?.existingRunId as string | undefined;
      if (existingRunId) return { runId: existingRunId };
    }
    throw err;
  }
}

export function getRunStatus(runId: string): Promise<RunStatusResponse> {
  return apiRequest<RunStatusResponse>(`/ingestion/runs/${runId}`);
}

export function cancelRun(runId: string): Promise<RunStatusResponse> {
  return apiRequest<RunStatusResponse>(`/ingestion/runs/${runId}/cancel`, { method: "POST" });
}

export function listRunHistory(page: number, pageSize = 20): Promise<RunHistoryPage> {
  return apiRequest<RunHistoryPage>("/ingestion/runs", { query: { page, pageSize } });
}

export function listRunFiles(runId: string): Promise<RunFileDetail[]> {
  return apiRequest<RunFileDetail[]>(`/ingestion/runs/${runId}/files`);
}

export function listRunLogs(runId: string, afterId?: number): Promise<RunLogLine[]> {
  return apiRequest<RunLogLine[]>(`/ingestion/runs/${runId}/logs`, {
    query: afterId !== undefined ? { afterId } : undefined,
  });
}
