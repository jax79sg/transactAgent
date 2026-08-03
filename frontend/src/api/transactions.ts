import { apiBaseUrl } from "../config";
import { apiRequest, toSnakeCase } from "./client";
import type { TransactionFilterState, TransactionPage, TransactionUpdatedResponse } from "./types";

export function listTransactions(filter: TransactionFilterState): Promise<TransactionPage> {
  return apiRequest<TransactionPage>("/transactions", { query: filter as Record<string, string | number> });
}

export function correctTransactionCategory(
  transactionId: string,
  categoryId: string,
): Promise<TransactionUpdatedResponse> {
  return apiRequest<TransactionUpdatedResponse>(`/transactions/${transactionId}/category`, {
    method: "PUT",
    body: { categoryId },
  });
}

/**
 * The export endpoint requires the same JWT as every other route (AR-1), so this
 * can't be a plain `<a href>` navigation (no way to attach an Authorization header
 * to a browser-initiated GET) -- fetches as a blob with the header, then triggers a
 * client-side download. Caught while implementing (functional-design left the exact
 * mechanism unresolved pending framework choice); resolved here.
 */
export async function downloadTransactionsCsv(filter: TransactionFilterState, token: string | null): Promise<void> {
  const { page: _page, pageSize: _pageSize, ...exportFilter } = filter;
  const url = new URL("/transactions/export.csv", apiBaseUrl);
  for (const [key, value] of Object.entries(exportFilter)) {
    if (value !== undefined && value !== "") url.searchParams.set(toSnakeCase(key), String(value));
  }

  const response = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`CSV export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = "transactions.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
