import { apiRequest } from "./client";
import type {
  BulkApproveResponse,
  BulkRejectResponse,
  DisagreementDTO,
  DisagreementPage,
  PendingCountResponse,
  ProposalDTO,
  ProposalPage,
} from "./types";

export type ProposalSortByOption = "date" | "amount" | "score" | "source";

export function listPendingProposals(
  page: number,
  pageSize = 20,
  sortBy?: ProposalSortByOption,
  sortDir?: "asc" | "desc",
): Promise<ProposalPage> {
  return apiRequest<ProposalPage>("/recategorization/proposals", { query: { page, pageSize, sortBy, sortDir } });
}

export function getPendingCount(): Promise<PendingCountResponse> {
  return apiRequest<PendingCountResponse>("/recategorization/proposals/pending-count");
}

export function approveProposal(proposalId: string): Promise<ProposalDTO> {
  return apiRequest<ProposalDTO>(`/recategorization/proposals/${proposalId}/approve`, { method: "POST" });
}

export function rejectProposal(proposalId: string): Promise<ProposalDTO> {
  return apiRequest<ProposalDTO>(`/recategorization/proposals/${proposalId}/reject`, { method: "POST" });
}

export function bulkApproveProposals(proposalIds: string[]): Promise<BulkApproveResponse> {
  return apiRequest<BulkApproveResponse>("/recategorization/proposals/bulk-approve", {
    method: "POST",
    body: { proposalIds },
  });
}

export function bulkRejectProposals(proposalIds: string[]): Promise<BulkRejectResponse> {
  return apiRequest<BulkRejectResponse>("/recategorization/proposals/bulk-reject", {
    method: "POST",
    body: { proposalIds },
  });
}

export function listPendingDisagreements(page: number, pageSize = 20): Promise<DisagreementPage> {
  return apiRequest<DisagreementPage>("/recategorization/disagreements", { query: { page, pageSize } });
}

export function resolveDisagreement(disagreementId: string, chosenCategoryId: string): Promise<DisagreementDTO> {
  return apiRequest<DisagreementDTO>(`/recategorization/disagreements/${disagreementId}/resolve`, {
    method: "POST",
    body: { chosenCategoryId },
  });
}

export function rejectDisagreement(disagreementId: string): Promise<DisagreementDTO> {
  return apiRequest<DisagreementDTO>(`/recategorization/disagreements/${disagreementId}/reject`, { method: "POST" });
}
