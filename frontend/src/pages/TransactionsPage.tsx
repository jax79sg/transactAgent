import * as Select from "@radix-ui/react-select";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { listCategories } from "../api/categories";
import { correctTransactionCategory, downloadTransactionsCsv, listTransactions } from "../api/transactions";
import type { CategoryDTO, GroupSummary, TransactionDTO, TransactionFilterState } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { filterStateToSearchParams, searchParamsToFilterState } from "../lib/urlFilterState";

/** Most-used categories first, so a manual correction rarely needs scrolling past
 * rarely-used ones -- alphabetical is the tiebreak for a stable, predictable order
 * among equally (or un-)used categories. */
export function byUsageThenName(categories: CategoryDTO[]): CategoryDTO[] {
  return [...categories].sort(
    (a, b) => b.transactionCount - a.transactionCount || a.name.localeCompare(b.name),
  );
}

/** ±30 days around the transaction: wide enough to catch the "other side" of a
 * transfer between accounts (the user's own motivating example for this feature),
 * narrow enough to keep the AI's context relevant rather than the whole history. */
function askAiDateWindow(transactionDate: string, days = 30): { dateFrom: string; dateTo: string } {
  const base = new Date(transactionDate);
  const from = new Date(base);
  from.setDate(from.getDate() - days);
  const to = new Date(base);
  to.setDate(to.getDate() + days);
  return { dateFrom: from.toISOString().slice(0, 10), dateTo: to.toISOString().slice(0, 10) };
}

export function askAiLinkFor(txn: TransactionDTO): string {
  const { dateFrom, dateTo } = askAiDateWindow(txn.transactionDate);
  const amount = txn.outFlow ?? txn.inFlow ?? "";
  const question = `What might this transaction "${txn.description}" for ${amount} ${txn.currency} on ${txn.transactionDate} be?`;
  const params = new URLSearchParams({ question, dateFrom, dateTo });
  return `/ask-ai?${params.toString()}`;
}

/** Must match the server's grouping key exactly (api_service/transactions/repository.py's
 * _GROUP_KEY_EXPRESSIONS) so each row lands under the right group header. */
export function groupKeyFor(txn: TransactionDTO, groupBy: NonNullable<TransactionFilterState["groupBy"]>): string {
  switch (groupBy) {
    case "category":
      return txn.category.name;
    case "bank":
      return txn.bankName;
    case "month":
      return txn.transactionDate.slice(0, 7);
    case "categorySource":
      return txn.categorySource;
  }
}

function CategorySelect({
  transaction,
  onCorrected,
}: {
  transaction: TransactionDTO;
  onCorrected: () => void;
}) {
  const { data: categories } = useQuery({ queryKey: ["categories"], queryFn: listCategories });
  const [editing, setEditing] = useState(false);

  const mutation = useMutation({
    mutationFn: (categoryId: string) => correctTransactionCategory(transaction.id, categoryId),
    onSuccess: () => {
      setEditing(false);
      onCorrected();
    },
  });

  const activeCategories = byUsageThenName((categories ?? []).filter((c) => c.active));

  if (!editing) {
    return (
      <button
        data-testid={`category-cell-${transaction.id}`}
        className={
          transaction.categorySource === "unsure"
            ? "rounded bg-amber-100 px-2 py-1 text-amber-800"
            : "rounded px-2 py-1 hover:bg-slate-100"
        }
        onClick={() => setEditing(true)}
      >
        {transaction.category.name}
      </button>
    );
  }

  return (
    <Select.Root
      defaultOpen
      onValueChange={(categoryId) => mutation.mutate(categoryId)}
      onOpenChange={(open) => !open && setEditing(false)}
    >
      <Select.Trigger data-testid={`category-select-${transaction.id}`} className="rounded border px-2 py-1">
        <Select.Value placeholder={transaction.category.name} />
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="rounded border bg-white shadow-lg">
          <Select.Viewport>
            {activeCategories.map((c) => (
              <Select.Item key={c.id} value={c.id} className="cursor-pointer px-3 py-1 hover:bg-slate-100">
                <Select.ItemText>{c.name}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

function TransactionRow({ txn, onCorrected }: { txn: TransactionDTO; onCorrected: () => void }) {
  return (
    <tr data-testid={`transaction-row-${txn.id}`} className="border-b border-slate-100">
      <td className="py-2">{txn.transactionDate}</td>
      <td>{txn.description}</td>
      <td>{txn.outFlow ?? ""}</td>
      <td>{txn.inFlow ?? ""}</td>
      <td>{txn.bankName}</td>
      <td>
        <CategorySelect transaction={txn} onCorrected={onCorrected} />
      </td>
      <td>
        {txn.conversionUnavailable ? "N/A" : `${txn.convertedAmountSgd}${txn.conversionIsApproximate ? " (approx.)" : ""}`}
      </td>
      <td>
        <Link
          to={askAiLinkFor(txn)}
          data-testid={`ask-ai-link-${txn.id}`}
          className="text-xs text-slate-500 hover:text-slate-800 hover:underline"
        >
          Ask AI
        </Link>
      </td>
    </tr>
  );
}

function GroupHeaderRow({ group }: { group: GroupSummary }) {
  return (
    <tr data-testid={`group-header-${group.groupKey}`} className="border-b border-slate-200 bg-slate-50">
      <td colSpan={8} className="py-2 font-medium">
        <div className="flex items-center justify-between">
          <span>{group.groupLabel}</span>
          <span className="font-normal text-slate-500">
            {group.transactionCount} txn{group.transactionCount === 1 ? "" : "s"} &middot; Out{" "}
            {group.subtotalOutFlowSgd} &middot; In {group.subtotalInFlowSgd}
          </span>
        </div>
      </td>
    </tr>
  );
}

export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filter: TransactionFilterState = searchParamsToFilterState(searchParams);
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const { data, isPending } = useQuery({
    queryKey: ["transactions", filter],
    queryFn: () => listTransactions(filter),
  });

  function updateFilter(patch: Partial<TransactionFilterState>) {
    setSearchParams(filterStateToSearchParams({ ...filter, ...patch, page: 1 }));
  }

  function toggleUnsureFilter() {
    updateFilter({ categorySource: filter.categorySource === "unsure" ? undefined : "unsure" });
  }

  async function handleExport() {
    await downloadTransactionsCsv(filter, token);
  }

  function refetchAfterCorrection() {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Transactions</h1>
        <input
          data-testid="text-search-input"
          placeholder="Search description..."
          className="rounded border border-slate-300 px-3 py-1 text-sm"
          value={filter.textSearch ?? ""}
          onChange={(e) => updateFilter({ textSearch: e.target.value || undefined })}
        />
        <button
          data-testid="unsure-filter-toggle"
          className={
            filter.categorySource === "unsure"
              ? "rounded bg-amber-500 px-3 py-1 text-sm text-white"
              : "rounded border border-slate-300 px-3 py-1 text-sm"
          }
          onClick={toggleUnsureFilter}
        >
          UNSURE only
        </button>
        <select
          data-testid="group-by-select"
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={filter.groupBy ?? ""}
          onChange={(e) => updateFilter({ groupBy: (e.target.value || undefined) as TransactionFilterState["groupBy"] })}
        >
          <option value="">No grouping</option>
          <option value="category">Group by category</option>
          <option value="bank">Group by bank</option>
          <option value="month">Group by month</option>
          <option value="categorySource">Group by source</option>
        </select>
        <button
          data-testid="export-csv-button"
          className="ml-auto rounded border border-slate-300 px-3 py-1 text-sm"
          onClick={handleExport}
        >
          Export CSV
        </button>
      </div>

      {isPending && <p>Loading...</p>}

      {data && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2">Date</th>
              <th>Description</th>
              <th>Out-flow</th>
              <th>In-flow</th>
              <th>Bank</th>
              <th>Category</th>
              <th>Converted (SGD)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filter.groupBy && data.groups
              ? [...data.groups]
                  .sort((a, b) => b.transactionCount - a.transactionCount)
                  .map((group) => (
                    <Fragment key={group.groupKey}>
                      <GroupHeaderRow group={group} />
                      {data.items
                        .filter((txn) => groupKeyFor(txn, filter.groupBy!) === group.groupKey)
                        .map((txn) => (
                          <TransactionRow key={txn.id} txn={txn} onCorrected={refetchAfterCorrection} />
                        ))}
                    </Fragment>
                  ))
              : data.items.map((txn) => (
                  <TransactionRow key={txn.id} txn={txn} onCorrected={refetchAfterCorrection} />
                ))}
          </tbody>
        </table>
      )}

      {data && data.items.length === 0 && <p className="text-slate-500">No matching transactions.</p>}

      {data && (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <button
            disabled={(filter.page ?? 1) <= 1}
            onClick={() => updateFilter({ page: (filter.page ?? 1) - 1 })}
            className="rounded border px-2 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {data.page} of {Math.max(1, Math.ceil(data.totalCount / data.pageSize))}
          </span>
          <button
            disabled={data.page * data.pageSize >= data.totalCount}
            onClick={() => updateFilter({ page: (filter.page ?? 1) + 1 })}
            className="rounded border px-2 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
