import { apiRequest } from "./client";
import type {
  AccountDTO,
  AccountListResponse,
  AccountUpdateRequest,
  AnchorRequest,
  AnchorResponse,
  MergeRequest,
} from "./types";

// Epic 13 (Account Balance at a Point in Time): account management. Paths are those fixed in the API design.

export function listAccounts(): Promise<AccountListResponse> {
  return apiRequest<AccountListResponse>("/accounts");
}

/** Rename and/or change the type. A PATCH: the request changes exactly the fields it names. */
export function updateAccount(accountId: string, request: AccountUpdateRequest): Promise<AccountDTO> {
  return apiRequest<AccountDTO>(`/accounts/${accountId}`, { method: "PATCH", body: request });
}

/** Set or replace the account's single anchor. The response carries the one it replaced, if any. */
export function setAnchor(accountId: string, request: AnchorRequest): Promise<AnchorResponse> {
  return apiRequest<AnchorResponse>(`/accounts/${accountId}/anchor`, { method: "PUT", body: request });
}

/** Merge `absorbedAccountId` into the account in the path (the survivor); returns the survivor. */
export function mergeAccounts(survivorId: string, request: MergeRequest): Promise<AccountDTO> {
  return apiRequest<AccountDTO>(`/accounts/${survivorId}/merge`, { method: "POST", body: request });
}
