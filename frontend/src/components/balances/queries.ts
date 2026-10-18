// Epic 13: the query keys and the two behaviours every account write shares. A successful write refreshes EVERYTHING
// that can show an account (the account list, every cached lookup, the chart and the warnings), so a new balance, a
// rename, a retype or a merge appears everywhere at once; and while any write is in flight the account actions are off.

import { useIsMutating, useQueryClient } from "@tanstack/react-query";

export const ACCOUNT_LIST_KEY = ["accounts", "list"] as const;
export const DISCREPANCIES_KEY = ["balances", "discrepancies"] as const;
export const WRITE_MUTATION_KEY = ["accounts", "write"] as const;

export function lookupKey(params: { date: string } | { month: string }) {
  return ["balances", "lookup", params] as const;
}

export function seriesKey(params: { from?: string; to?: string; granularity?: string }) {
  return ["balances", "series", params] as const;
}

/** Invalidates `["accounts"]` and `["balances"]` together (prefix match). */
export function useRefreshBalanceData(): () => Promise<unknown> {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["balances"] }),
    ]);
}

/** True while any account write (balance, rename, type, merge) is in flight. */
export function useIsWriting(): boolean {
  return useIsMutating({ mutationKey: WRITE_MUTATION_KEY }) > 0;
}
