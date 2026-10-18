import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAccounts } from "../../api/accounts";
import { anchorSavedMessage, nextAccountNeedingBalance, localToday } from "../../lib/balances";
import { AccountsSection } from "./AccountsSection";
import { BalanceChart } from "./BalanceChart";
import { BalanceDialog, type BalanceSaveResult } from "./BalanceDialog";
import { BalanceLookup } from "./BalanceLookup";
import { DiscrepancyPanel } from "./DiscrepancyPanel";
import { ACCOUNT_LIST_KEY } from "./queries";

/** One open balance dialog: which account, the date it starts on, and the accounts already done in this run. */
type Entry = { accountId: string; date: string; handled: string[] };

// Epic 13 (FR-AB-13): the Balances tab on the Dashboard. It composes the warnings line, the lookup, the chart and the
// accounts, each with its own query and its own failure state, so one failing never blanks the others. What it owns is
// what two of them share: the API's "today" (learned from the lookup) and the balance dialog, which opens from both the
// "Anchor required" prompt and the accounts list, with one status line for the outcome of the last action.
export function BalancesTab() {
  const [serverToday, setServerToday] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [entry, setEntry] = useState<Entry | null>(null);
  const [lastEntryDate, setLastEntryDate] = useState<string | null>(null);
  const accounts = useQuery({ queryKey: ACCOUNT_LIST_KEY, queryFn: listAccounts, retry: false }).data?.items ?? [];

  const account = entry ? accounts.find((a) => a.id === entry.accountId) : undefined;

  function openBalanceDialog(accountId: string) {
    setEntry({ accountId, date: lastEntryDate ?? serverToday ?? localToday(), handled: [] });
  }

  function saved({ account: savedAccount, response, saveAndNext }: BalanceSaveResult) {
    setStatusMessage(anchorSavedMessage(savedAccount.name, savedAccount.currency, response));
    setLastEntryDate(response.anchor.asOfDate);
    const handled = [...(entry?.handled ?? []), savedAccount.id];
    const next = saveAndNext ? nextAccountNeedingBalance(accounts, handled) : null;
    setEntry(next ? { accountId: next.id, date: response.anchor.asOfDate, handled } : null);
  }

  return (
    <div data-testid="balances-tab">
      <DiscrepancyPanel />
      <BalanceLookup onSetBalance={openBalanceDialog} onToday={setServerToday} />
      <BalanceChart today={serverToday} />
      <AccountsSection statusMessage={statusMessage} onSetBalance={openBalanceDialog} onMessage={setStatusMessage} />

      {entry && account && (
        <BalanceDialog
          key={account.id}
          account={account}
          defaultDate={entry.date}
          maxDate={serverToday ?? localToday()}
          canSaveAndNext={nextAccountNeedingBalance(accounts, [...entry.handled, account.id]) !== null}
          onClose={() => setEntry(null)}
          onSaved={saved}
          onGone={(message) => {
            setStatusMessage(message);
            setEntry(null);
          }}
        />
      )}
    </div>
  );
}
