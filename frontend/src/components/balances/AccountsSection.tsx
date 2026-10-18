import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAccounts } from "../../api/accounts";
import type { AccountDTO, AccountType } from "../../api/types";
import { balanceErrorMessage, pluralize, TYPE_LABELS } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";
import { formatMoney } from "../../lib/money";
import { ChangeTypeDialog } from "./ChangeTypeDialog";
import { MergeDialog } from "./MergeDialog";
import { RenameDialog } from "./RenameDialog";
import { ACCOUNT_LIST_KEY, useIsWriting } from "./queries";

const GROUPS: { type: AccountType; title: string }[] = [
  { type: "deposit", title: "Savings and current accounts" },
  { type: "credit_card", title: "Credit cards" },
  { type: "unknown", title: "Other (type unknown)" },
];

const ACTION =
  "min-h-[32px] rounded border border-slate-300 px-2 py-0.5 text-sm disabled:opacity-50 dark:border-slate-600";

type OpenDialog = { kind: "rename" | "type" | "merge"; accountId: string } | null;

function figures(account: AccountDTO): string {
  const balance = account.anchor
    ? `Balance entered: ${formatMoney(account.anchor.balance, account.currency)} on ${formatDay(account.anchor.asOfDate, true)}`
    : account.canHaveAnchor
      ? "No balance entered"
      : "Not in balances";
  const last = account.latestTransactionDate ? `last transaction ${formatDay(account.latestTransactionDate, true)}` : "no transactions";
  return [
    balance,
    pluralize(account.statementCount, "statement", "statements"),
    pluralize(account.transactionCount, "transaction", "transactions"),
    pluralize(account.closingBalanceCount, "printed closing balance", "printed closing balances"),
    last,
  ].join(" · ");
}

// Epic 13 (US-13.2, US-13.3, Question 4 = A): every account in a wrapping list, so it works at any width without a
// second layout. Same-named accounts are told apart by their identifier and counts. Each action opens a small dialog;
// the balance dialog is owned by the tab (it is also opened from the "Anchor required" prompt), so it is requested
// through `onSetBalance`. The status line, a polite live region, says what the last action did.
export function AccountsSection({
  statusMessage,
  onSetBalance,
  onMessage,
}: {
  statusMessage: string | null;
  onSetBalance: (accountId: string) => void;
  onMessage: (message: string) => void;
}) {
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const writing = useIsWriting();
  const query = useQuery({ queryKey: ACCOUNT_LIST_KEY, queryFn: listAccounts, retry: false });
  const accounts = query.data?.items ?? [];
  const open = dialog ? accounts.find((account) => account.id === dialog.accountId) : undefined;

  const done = (message: string) => {
    setDialog(null);
    onMessage(message);
  };

  return (
    <section data-testid="accounts-section" className="mb-6">
      <h3 className="mb-2 font-medium">Accounts</h3>
      <p data-testid="account-status-message" role="status" aria-live="polite" className="mb-2 min-h-[1.25rem] text-sm text-green-800 dark:text-green-300">
        {statusMessage}
      </p>

      {query.isPending && (
        <p data-testid="accounts-loading" className="text-sm text-slate-500 dark:text-slate-400">
          Loading accounts&hellip;
        </p>
      )}
      {query.isError && (
        <p data-testid="accounts-error" role="alert" className="text-sm text-red-600 dark:text-red-400">
          {balanceErrorMessage(query.error)}{" "}
          <button type="button" data-testid="accounts-retry" onClick={() => query.refetch()} className="underline">
            Try again
          </button>
        </p>
      )}
      {query.isSuccess && accounts.length === 0 && (
        <p data-testid="accounts-empty" className="text-sm text-slate-500 dark:text-slate-400">
          No accounts yet. They are created when statements are ingested.
        </p>
      )}

      {GROUPS.map((group) => {
        const members = accounts.filter((account) => account.type === group.type);
        if (members.length === 0) return null;
        return (
          <div key={group.type} data-testid={`accounts-group-${group.type}`} className="mb-4">
            <h4 className="mb-1 text-sm font-medium text-slate-600 dark:text-slate-300">{group.title}</h4>
            <ul>
              {members.map((account) => (
                <li
                  key={account.id}
                  data-testid={`account-row-${account.id}`}
                  className="border-b border-slate-100 py-2 dark:border-slate-800"
                >
                  <div className="font-medium">
                    {account.name}
                    {account.accountIdentifier && (
                      <span className="ml-2 font-normal text-slate-500 dark:text-slate-400">{account.accountIdentifier}</span>
                    )}
                  </div>
                  <div className="text-sm text-slate-600 dark:text-slate-300">
                    {account.bankName} &middot; {TYPE_LABELS[account.type]}
                    {account.typeSetByUser ? " (set by you)" : ""} &middot; {account.currency}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{figures(account)}</div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {account.canHaveAnchor && (
                      <button
                        type="button"
                        data-testid={`account-set-balance-${account.id}`}
                        disabled={writing}
                        onClick={() => onSetBalance(account.id)}
                        className={ACTION}
                      >
                        {account.anchor ? "Replace balance" : "Set balance"}
                      </button>
                    )}
                    <button
                      type="button"
                      data-testid={`account-rename-${account.id}`}
                      disabled={writing}
                      onClick={() => setDialog({ kind: "rename", accountId: account.id })}
                      className={ACTION}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      data-testid={`account-change-type-${account.id}`}
                      disabled={writing}
                      onClick={() => setDialog({ kind: "type", accountId: account.id })}
                      className={ACTION}
                    >
                      Change type
                    </button>
                    <button
                      type="button"
                      data-testid={`account-merge-${account.id}`}
                      disabled={writing}
                      onClick={() => setDialog({ kind: "merge", accountId: account.id })}
                      className={ACTION}
                    >
                      Merge into&hellip;
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      {open && dialog?.kind === "rename" && <RenameDialog account={open} onClose={() => setDialog(null)} onDone={done} />}
      {open && dialog?.kind === "type" && <ChangeTypeDialog account={open} onClose={() => setDialog(null)} onDone={done} />}
      {open && dialog?.kind === "merge" && <MergeDialog absorbed={open} accounts={accounts} onClose={() => setDialog(null)} onDone={done} />}
    </section>
  );
}
