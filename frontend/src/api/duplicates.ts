import { apiRequest } from "./client";
import type {
  DuplicateComparison,
  DuplicatePair,
  DuplicatePairPage,
  OverrideResponse,
  PendingPairCountResponse,
  RemovalRequest,
  ScanStatus,
} from "./types";

// Probable Duplicate Statement Detection (Epic 14). Paths are the ones fixed at Frontend Functional Design and
// implemented by api-service's duplicates/router.py.

export function listPairs(page: number, pageSize = 20): Promise<DuplicatePairPage> {
  return apiRequest<DuplicatePairPage>("/duplicates/pairs", { query: { page, pageSize } });
}

export function getPendingPairCount(): Promise<PendingPairCountResponse> {
  return apiRequest<PendingPairCountResponse>("/duplicates/pairs/pending-count");
}

export function getComparison(comparisonId: string): Promise<DuplicateComparison> {
  return apiRequest<DuplicateComparison>(`/duplicates/comparisons/${comparisonId}`);
}

export function requestRemoval(pairId: string, body: RemovalRequest): Promise<DuplicatePair> {
  return apiRequest<DuplicatePair>(`/duplicates/pairs/${pairId}/remove`, { method: "POST", body });
}

export function dismissPair(pairId: string): Promise<DuplicatePair> {
  return apiRequest<DuplicatePair>(`/duplicates/pairs/${pairId}/dismiss`, { method: "POST" });
}

export function overrideSkippedFile(comparisonId: string): Promise<OverrideResponse> {
  return apiRequest<OverrideResponse>(`/duplicates/comparisons/${comparisonId}/override`, { method: "POST" });
}

export function getScanStatus(): Promise<ScanStatus> {
  return apiRequest<ScanStatus>("/duplicates/scan-status");
}

export function requestRecheck(): Promise<ScanStatus> {
  return apiRequest<ScanStatus>("/duplicates/recheck", { method: "POST" });
}
