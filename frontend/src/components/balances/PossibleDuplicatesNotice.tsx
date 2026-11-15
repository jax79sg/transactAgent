import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAccounts } from "../../api/accounts";
import type { AccountDTO } from "../../api/types";
import { findPossibleDuplicates, joinList } from "../../lib/balances";
import { MergeDialog } from "./MergeDialog";
import { ACCOUNT_LIST_KEY, useIsWriting } from "./queries";

const quoted = (name: string): string => `“${name}”`;

function describe(group: readonly AccountDTO[]): string {
  const names = joinList(group.map((account) => quoted(account.name)));
  const withBalance = group.filter((account) => account.anchor !== null).length;
  if (withBalance === 2 && group.length === 2) {
    return `${names} have the same account number. A balance is entered on each, so the combined total counts this account twice. If they are one account, merge them.`;
  }
  if (withBalance >= 2) {
    return `${names} have the same account number. More than one of them has a balance entered, so the combined total counts this account more than once. If they are one account, merge them.`;
  }
  return `${names} have the same account number, so they may be one account listed twice. If they are, merge them.`;
}

// Issue #65 (DBS 6220 and DBS / POSB 6220): one real account listed twice, because its statements spell the bank two
// ways, with a balance entered on each, so the total counted it twice. Matching stays conservative on purpose (the
// design has the owner merge, never the app guess), so this is how the owner is told. The button opens the ordinary
// Merge dialog on the account with fewer statements; which account to keep, and which balance, stay the owner's choice.
export function PossibleDuplicatesNotice({ onMessage }: { onMessage: (message: string) => void }) {
  const accounts = useQuery({ queryKey: ACCOUNT_LIST_KEY, queryFn: listAccounts, retry: false }).data?.items ?? [];
  const writing = useIsWriting();
  const [mergingId, setMergingId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const groups = findPossibleDuplicates(accounts);
  const merging = mergingId ? accounts.find((account) => account.id === mergingId) : undefined;

  return (
    <>
      {groups.length > 0 && (
        <div
          data-testid="possible-duplicates"
          role="note"
          className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <p className="mb-2 font-medium">Possible duplicate accounts</p>
          {groups.map((group) => (
            <div key={group[0].id} className="mb-2 last:mb-0">
              <p>{describe(group)}</p>
              <button
                type="button"
                data-testid={`merge-duplicates-${group[0].id}`}
                aria-label={`Review and merge ${joinList(group.map((account) => quoted(account.name)))}`}
                disabled={writing}
                onClick={() => setMergingId(group[group.length - 1].id)}
                className="mt-1 min-h-[32px] rounded border border-amber-400 px-2 py-0.5 text-sm disabled:opacity-50 dark:border-amber-700"
              >
                Review and merge
              </button>
            </div>
          ))}
        </div>
      )}
      {outcome && (
        <p data-testid="duplicates-merged-message" role="status" className="mb-4 text-sm text-green-800 dark:text-green-300">
          {outcome}
        </p>
      )}
      {merging && (
        <MergeDialog
          absorbed={merging}
          accounts={accounts}
          onClose={() => setMergingId(null)}
          onDone={(message) => {
            setMergingId(null);
            setOutcome(message);
            onMessage(message);
          }}
        />
      )}
    </>
  );
}
