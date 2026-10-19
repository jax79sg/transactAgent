import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { getDiscrepancies } from "../../api/balances";
import type { AccountDiscrepancyDTO, PeriodGapDTO, StatementDifferenceDTO } from "../../api/types";
import { describeDiscrepancyCount, pluralize } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";
import { formatAmount, formatMoney, isNegativeAmount, toCents } from "../../lib/money";
import { DISCREPANCIES_KEY } from "./queries";

const byName = (a: AccountDiscrepancyDTO, b: AccountDiscrepancyDTO): number => a.name.toLowerCase().localeCompare(b.name.toLowerCase());

/** A signed difference with its meaning in words, so the sign needs no decoding. */
function signedWords(amount: string, currency: string): string {
  const cents = toCents(amount);
  const sign = cents > 0n ? "+" : "";
  const words = cents > 0n ? " (statement shows more)" : cents < 0n ? " (statement shows less)" : "";
  return `${sign}${formatMoney(amount, currency)}${words}`;
}

function StatementDifferences({ account, rows }: { account: AccountDiscrepancyDTO; rows: StatementDifferenceDTO[] }) {
  const sorted = [...rows].sort((a, b) => a.closingDate.localeCompare(b.closingDate));
  return (
    <div className="mt-2">
      <h5 className="text-sm font-medium">Statements that differ from your entered balance</h5>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Statements that differ from your entered balance, {account.name}</caption>
          <thead>
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="py-1 pr-3">Statement</th>
              <th className="py-1 pr-3">Statement says</th>
              <th className="py-1 pr-3">Worked out from your balance</th>
              <th className="py-1">Difference</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr
                key={`${row.statementId ?? "none"}-${row.closingDate}`}
                data-testid={`statement-difference-row-${row.statementId ?? row.closingDate}`}
                className="border-b border-slate-100 dark:border-slate-800"
              >
                <td className="py-1 pr-3 whitespace-nowrap">Statement closing {formatDay(row.closingDate, true)}</td>
                <td className="py-1 pr-3 whitespace-nowrap">{formatAmount(row.printedBalance)}</td>
                <td className="py-1 pr-3 whitespace-nowrap">{formatAmount(row.computedBalance)}</td>
                <td className={`py-1 whitespace-nowrap ${isNegativeAmount(row.difference) ? "text-red-700 dark:text-red-400" : ""}`}>
                  {signedWords(row.difference, account.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        A wrong entered balance, or missing transactions before this date. Correct your entered balance and these disappear.
      </p>
    </div>
  );
}

function PeriodGaps({ account, rows }: { account: AccountDiscrepancyDTO; rows: PeriodGapDTO[] }) {
  const sorted = [...rows].sort((a, b) => a.fromDate.localeCompare(b.fromDate));
  return (
    <div className="mt-3">
      <h5 className="text-sm font-medium">Intervals where transactions don&apos;t explain the change</h5>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Intervals where transactions do not explain the change, {account.name}</caption>
          <thead>
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="py-1 pr-3">Interval</th>
              <th className="py-1 pr-3">Statements say it changed by</th>
              <th className="py-1 pr-3">Transactions changed it by</th>
              <th className="py-1">Gap</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr
                key={`${row.fromStatementId ?? row.fromDate}-${row.toStatementId ?? row.toDate}`}
                data-testid={`period-gap-row-${row.fromStatementId ?? row.fromDate}-${row.toStatementId ?? row.toDate}`}
                className="border-b border-slate-100 dark:border-slate-800"
              >
                <td className="py-1 pr-3 whitespace-nowrap">
                  {formatDay(row.fromDate, true)} to {formatDay(row.toDate, true)}
                </td>
                <td className="py-1 pr-3 whitespace-nowrap">{formatAmount(row.printedChange)}</td>
                <td className="py-1 pr-3 whitespace-nowrap">{formatAmount(row.transactionNet)}</td>
                <td className={`py-1 whitespace-nowrap ${isNegativeAmount(row.gap) ? "text-red-700 dark:text-red-400" : ""}`}>
                  {signedWords(row.gap, account.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Transactions are probably missing or dated wrongly in this interval. This does not depend on your entered balance
        and stays until the transactions are fixed.
      </p>
    </div>
  );
}

// Epic 13 (US-13.6, Question 3 = A): one line at the top of the Balances tab, details only on request. The warning
// never blocks or changes a figure, and its own failure never disturbs the rest of the tab. Nothing is shown until an
// account has an entered balance, because only then is anything checked.
export function DiscrepancyPanel() {
  const [open, setOpen] = useState(false);
  const query = useQuery({ queryKey: DISCREPANCIES_KEY, queryFn: getDiscrepancies, retry: false });

  if (query.isError) {
    return (
      <p data-testid="discrepancy-error" className="mb-4 text-sm text-slate-500 dark:text-slate-400">
        Couldn&apos;t check statement differences.{" "}
        <button type="button" data-testid="discrepancy-retry" onClick={() => query.refetch()} className="underline">
          Try again
        </button>
      </p>
    );
  }
  const data = query.data;
  if (!data || data.accountsChecked === 0) return null;

  if (data.items.length === 0) {
    return (
      <p data-testid="discrepancy-summary" className="mb-4 text-sm text-green-800 dark:text-green-300">
        Your statements agree with your balances ({pluralize(data.accountsChecked, "account", "accounts")} checked).
      </p>
    );
  }

  const accounts = [...data.items].sort(byName);
  return (
    <section className="mb-4">
      <div className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
        <span data-testid="discrepancy-summary">{describeDiscrepancyCount(data.items.length)}</span>{" "}
        <button
          type="button"
          data-testid="discrepancy-toggle"
          aria-expanded={open}
          aria-controls="discrepancy-details"
          onClick={() => setOpen(!open)}
          className="underline"
        >
          {open ? "Hide details" : "Show details"}
        </button>
      </div>
      {open && (
        <div id="discrepancy-details" data-testid="discrepancy-details" className="mt-2 text-sm">
          {accounts.map((account) => (
            <div key={account.accountId} data-testid={`discrepancy-account-${account.accountId}`} className="mb-4">
              <h4 className="font-medium">
                {account.name} ({account.currency}): {pluralize(account.statementsChecked, "statement", "statements")} and{" "}
                {pluralize(account.periodsChecked, "statement-to-statement interval", "statement-to-statement intervals")} checked
              </h4>
              {account.statementDifferences.length > 0 && <StatementDifferences account={account} rows={account.statementDifferences} />}
              {account.periodGaps.length > 0 && <PeriodGaps account={account} rows={account.periodGaps} />}
            </div>
          ))}
          <p data-testid="discrepancy-footer" className="text-xs text-slate-500 dark:text-slate-400">
            Differences larger than {formatAmount(data.tolerance)} are listed; change this in{" "}
            <Link to="/settings" className="underline">
              Settings under Balances
            </Link>
            . Only accounts with an entered balance are checked.
          </p>
        </div>
      )}
    </section>
  );
}
