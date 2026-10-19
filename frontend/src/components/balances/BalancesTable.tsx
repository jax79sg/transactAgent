import type { AccountBalanceDTO, BalancesResponse } from "../../api/types";
import { describeBasis, describeExclusions, pluralize } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";
import { formatAmount, isNegativeAmount } from "../../lib/money";
import { useIsWriting } from "./queries";

const NEGATIVE = "text-red-700 dark:text-red-400";

function SgdCell({ account }: { account: AccountBalanceDTO }) {
  if (account.status === "fx_unavailable") {
    return (
      <span data-testid={`balance-status-${account.accountId}`} className="text-amber-700 dark:text-amber-400">
        Unavailable: no exchange rate
      </span>
    );
  }
  const negative = account.balanceSgd !== null && isNegativeAmount(account.balanceSgd);
  return (
    <>
      <span data-testid={`balance-sgd-${account.accountId}`} className={`font-medium ${negative ? NEGATIVE : ""}`}>
        {account.isApproximate ? "≈ " : ""}
        {formatAmount(account.balanceSgd)}
      </span>
      {account.isApproximate && account.fxRateDate && (
        <div data-testid={`balance-approx-${account.accountId}`} className="text-xs text-slate-500 dark:text-slate-400">
          approximate: exchange rate of {formatDay(account.fxRateDate, true)}
        </div>
      )}
    </>
  );
}

// Epic 13 (US-13.4): one row per deposit account with its state in words (and colour), the combined total, and every
// exclusion stated beside it. A real table so the numbers align; it scrolls sideways inside its box on a phone.
export function BalancesTable({
  response,
  onSetBalance,
}: {
  response: BalancesResponse;
  onSetBalance: (accountId: string) => void;
}) {
  const writing = useIsWriting();
  const { accounts } = response;

  if (accounts.length === 0) {
    return (
      <p data-testid="balances-empty-state" className="text-sm text-slate-500 dark:text-slate-400">
        No savings or current accounts yet. They appear here once statements have been ingested. Credit cards are never
        part of balances.
      </p>
    );
  }

  const showNative = accounts.some((account) => account.currency !== "SGD");
  const columnCount = 4 + (showNative ? 1 : 0);
  const exclusions = describeExclusions(response.excluded);

  return (
    <div>
      {response.combinedIncludesCount === 0 && (
        <p data-testid="balances-explainer" className="mb-2 text-sm text-slate-600 dark:text-slate-300">
          An anchor is a balance you know to be real on a date, such as one from your banking app. The app works out every
          other date from it.
        </p>
      )}
      <div className="overflow-x-auto">
        <table data-testid="balances-table" className="w-full text-sm">
          <caption className="sr-only">Balances by account</caption>
          <thead>
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="py-1 pr-3">Account</th>
              {showNative && <th className="py-1 pr-3">Balance</th>}
              <th className="py-1 pr-3">SGD</th>
              <th className="py-1 pr-3">Worked from</th>
              <th className="py-1">Last transaction</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr
                key={account.accountId}
                data-testid={`balance-row-${account.accountId}`}
                className="border-b border-slate-100 align-top dark:border-slate-800"
              >
                <td className="py-2 pr-3">
                  <div className="font-medium">{account.name}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{account.bankName}</div>
                </td>
                {account.status === "anchor_required" ? (
                  <td colSpan={columnCount - 2} className="py-2 pr-3">
                    <span
                      data-testid={`balance-status-${account.accountId}`}
                      className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                    >
                      Anchor required
                    </span>{" "}
                    <button
                      type="button"
                      data-testid={`set-balance-${account.accountId}`}
                      disabled={writing}
                      onClick={() => onSetBalance(account.accountId)}
                      className="ml-2 min-h-[32px] rounded border border-slate-300 px-2 py-0.5 text-sm disabled:opacity-50 dark:border-slate-600"
                    >
                      Set balance
                    </button>
                  </td>
                ) : (
                  <>
                    {showNative && (
                      <td data-testid={`balance-native-${account.accountId}`} className="py-2 pr-3 whitespace-nowrap">
                        {formatAmount(account.balanceNative)} {account.currency}
                      </td>
                    )}
                    <td className="py-2 pr-3 whitespace-nowrap">
                      <SgdCell account={account} />
                    </td>
                    <td data-testid={`balance-basis-${account.accountId}`} className="py-2 pr-3">
                      {account.basis ? `From ${describeBasis(account.basis)}` : "—"}
                    </td>
                  </>
                )}
                <td className="py-2 whitespace-nowrap">
                  {account.latestTransactionDate ? formatDay(account.latestTransactionDate, true) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p data-testid="combined-total" className="mt-3 text-sm font-medium">
        {response.combinedTotalSgd === null
          ? "No account has a balance yet. Enter one for each account to see a total."
          : `Combined total (${pluralize(response.combinedIncludesCount, "account", "accounts")}): SGD ${formatAmount(response.combinedTotalSgd)}`}
      </p>
      {exclusions && (
        <p data-testid="combined-exclusions" className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {exclusions}
        </p>
      )}
      {response.hasApproximate && (
        <p data-testid="balances-approx-note" className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          &asymp; marks a figure converted at the nearest earlier exchange rate we have.
        </p>
      )}
    </div>
  );
}
