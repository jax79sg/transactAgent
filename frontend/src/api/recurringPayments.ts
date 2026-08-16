import { apiRequest } from "./client";
import type {
  BulkImportResponse,
  BulkImportRow,
  DetectionSuggestionDTO,
  RecurringPaymentCreateRequest,
  RecurringPaymentDTO,
  RecurringPaymentMatchDTO,
  RecurringPaymentsStatusSummaryDTO,
  RecurringPaymentUpdateRequest,
} from "./types";

export function listRecurringPayments(): Promise<RecurringPaymentDTO[]> {
  return apiRequest<RecurringPaymentDTO[]>("/recurring-payments");
}

export function createRecurringPayment(request: RecurringPaymentCreateRequest): Promise<RecurringPaymentDTO> {
  return apiRequest<RecurringPaymentDTO>("/recurring-payments", { method: "POST", body: request });
}

export function updateRecurringPayment(id: string, request: RecurringPaymentUpdateRequest): Promise<RecurringPaymentDTO> {
  return apiRequest<RecurringPaymentDTO>(`/recurring-payments/${id}`, { method: "PUT", body: request });
}

export function deleteRecurringPayment(id: string): Promise<void> {
  return apiRequest<void>(`/recurring-payments/${id}`, { method: "DELETE" });
}

export function bulkImportRecurringPayments(rows: BulkImportRow[]): Promise<BulkImportResponse> {
  return apiRequest<BulkImportResponse>("/recurring-payments/bulk-import", { method: "POST", body: { rows } });
}

export function listPendingMatches(): Promise<RecurringPaymentMatchDTO[]> {
  return apiRequest<RecurringPaymentMatchDTO[]>("/recurring-payments/matches");
}

export function approveMatch(matchId: string): Promise<RecurringPaymentMatchDTO> {
  return apiRequest<RecurringPaymentMatchDTO>(`/recurring-payments/matches/${matchId}/approve`, { method: "POST" });
}

export function rejectMatch(matchId: string): Promise<RecurringPaymentMatchDTO> {
  return apiRequest<RecurringPaymentMatchDTO>(`/recurring-payments/matches/${matchId}/reject`, { method: "POST" });
}

export function listDetectionSuggestions(): Promise<DetectionSuggestionDTO[]> {
  return apiRequest<DetectionSuggestionDTO[]>("/recurring-payments/detection-suggestions");
}

export function dismissDetectionSuggestion(id: string): Promise<void> {
  return apiRequest<void>(`/recurring-payments/detection-suggestions/${id}/dismiss`, { method: "POST" });
}

export function addFromDetectionSuggestion(id: string): Promise<RecurringPaymentDTO> {
  return apiRequest<RecurringPaymentDTO>(`/recurring-payments/detection-suggestions/${id}/add`, {
    method: "POST",
    body: {},
  });
}

export function getRecurringPaymentsStatus(): Promise<RecurringPaymentsStatusSummaryDTO> {
  return apiRequest<RecurringPaymentsStatusSummaryDTO>("/recurring-payments/status");
}
