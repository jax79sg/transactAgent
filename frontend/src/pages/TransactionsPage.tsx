import * as Select from "@radix-ui/react-select";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { listCategories } from "../api/categories";
import { correctTransactionCategory, downloadTransactionsCsv, listBanks, listTransactions } from "../api/transactions";
import type { CategoryDTO, GroupSummary, SortByOption, TransactionDTO, TransactionFilterState } from "../api/types";
import { SortableTh } from "../components/SortableTh";
import { useAuth } from "../context/AuthContext";
import { filterStateToSearchParams, searchParamsToFilterState } from "../lib/urlFilterState";

/** The 10 most-used categories first (ties broken alphabetically), so a manual
 * correction rarely needs scrolling past rarely-used ones -- everything else is
 * sorted purely alphabetically below them, rather than continuing the usage sort,
 * so a category the user is hunting for by name (rather than by how common it is)
 * is easy to scan for once past the top 10. */
const TOP_USED_CATEGORY_COUNT = 10;

export function byUsageThenName(categories: CategoryDTO[]): CategoryDTO[] {
  const byUsage = [...categories].sort(
    (a, b) => b.transactionCount - a.transactionCount || a.name.localeCompare(b.name),
  );
  const topUsed = byUsage.slice(0, TOP_USED_CATEGORY_COUNT);
  const rest = byUsage.slice(TOP_USED_CATEGORY_COUNT).sort((a, b) => a.name.localeCompare(b.name));
  return [...topUsed, ...rest];
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
  const { data: categories, refetch: refetchCategories } = useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
  });
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
            ? "rounded bg-amber-100 px-2 py-1 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            : "rounded px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-800"
        }
        onClick={() => {
          setEditing(true);
          // The category list is fetched once per row-mount and the app disables
          // refetch-on-window-focus globally, so a category added/renamed elsewhere
          // (another tab, or earlier in a long-lived session) wouldn't otherwise
          // show up here until a full page reload -- refetch right as the dropdown
          // opens so what the user picks from is always current.
          void refetchCategories();
        }}
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
      <Select.Trigger
        data-testid={`category-select-${transaction.id}`}
        className="rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
      >
        <Select.Value placeholder={transaction.category.name} />
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="max-h-80 rounded border bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800"
          position="popper"
        >
          {/* Radix's own viewport already scrolls internally (overflow-y: auto), but
              with no visible affordance a list this long (50+ categories, alphabetical
              after the used ones) just looks like it ends at the screen edge on
              platforms with auto-hiding scrollbars -- a real user report: a just-added
              category "wasn't showing up" when it was actually there, just below the
              fold with nothing hinting more existed. These buttons are Radix's built-in
              fix: a visible chevron at each edge, shown only when there's more to
              scroll that way, that also auto-scrolls on hover. */}
          <Select.ScrollUpButton className="flex items-center justify-center bg-white py-1 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            ▲
          </Select.ScrollUpButton>
          <Select.Viewport>
            {activeCategories.map((c) => (
              <Select.Item
                key={c.id}
                value={c.id}
                className="cursor-pointer px-3 py-1 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700"
              >
                <Select.ItemText>{c.name}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
          <Select.ScrollDownButton className="flex items-center justify-center bg-white py-1 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            ▼
          </Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

/** Epic 9 (Local Embedding-Based Semantic Similarity, US-9.1, FR-7): a quiet,
 * purely informational processing-status indicator -- "has this transaction's
 * embedding been computed and stored," NOT a claim about match quality or that a
 * precedent was found. Deliberately not styled to compete for attention with
 * anything actionable elsewhere on the page (contrast NavBar's count badges). */
function EmbeddingStatusBadge({ status }: { status: TransactionDTO["embeddingStatus"] }) {
  const completed = status === "completed";
  return (
    <span
      data-testid="embedding-status-badge"
      title={completed ? "Embedding: computed" : "Embedding: pending"}
      aria-label={completed ? "Embedding computed" : "Embedding pending"}
      className={`ml-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${
        completed ? "bg-emerald-400" : "bg-slate-300 dark:bg-slate-600"
      }`}
    />
  );
}

function TransactionRow({
  txn,
  index,
  onCorrected,
}: {
  txn: TransactionDTO;
  index: number;
  onCorrected: () => void;
}) {
  return (
    <tr
      data-testid={`transaction-row-${txn.id}`}
      className={`border-b border-slate-100 dark:border-slate-800 ${
        index % 2 === 1 ? "bg-slate-100 dark:bg-slate-800" : "bg-white dark:bg-slate-900"
      }`}
    >
      <td className="py-2">{txn.transactionDate}</td>
      <td>
        {txn.description}
        <EmbeddingStatusBadge status={txn.embeddingStatus} />
      </td>
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
          className="text-xs text-slate-500 hover:text-slate-800 hover:underline dark:text-slate-400 dark:hover:text-slate-200"
        >
          Ask AI
        </Link>
      </td>
    </tr>
  );
}

function GroupHeaderRow({ group }: { group: GroupSummary }) {
  return (
    <tr
      data-testid={`group-header-${group.groupKey}`}
      className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800"
    >
      <td colSpan={8} className="py-2 font-medium">
        <div className="flex items-center justify-between">
          <span>{group.groupLabel}</span>
          <span className="font-normal text-slate-500 dark:text-slate-400">
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

  const { data: banks, refetch: refetchBanks } = useQuery({ queryKey: ["banks"], queryFn: listBanks });
  // Same queryKey CategorySelect uses per-row -- react-query dedupes this into one
  // shared cached request rather than fetching the category list again.
  const { data: categories, refetch: refetchCategories } = useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
  });

  function updateFilter(patch: Partial<TransactionFilterState>) {
    // page: 1 is a default that applies when a filter changes (e.g. search text,
    // grouping) -- it must come BEFORE ...patch so an explicit page change (the
    // pagination buttons passing { page: n }) isn't immediately clobbered back to 1.
    setSearchParams(filterStateToSearchParams({ ...filter, page: 1, ...patch }));
  }

  function toggleUnsureFilter() {
    updateFilter({ categorySource: filter.categorySource === "unsure" ? undefined : "unsure" });
  }

  function handleSort(sortBy: SortByOption, sortDir: "asc" | "desc") {
    updateFilter({ sortBy, sortDir });
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
          className="rounded border border-slate-300 px-3 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          value={filter.textSearch ?? ""}
          onChange={(e) => updateFilter({ textSearch: e.target.value || undefined })}
        />
        <button
          data-testid="unsure-filter-toggle"
          className={
            filter.categorySource === "unsure"
              ? "rounded bg-amber-500 px-3 py-1 text-sm text-white dark:bg-amber-600"
              : "rounded border border-slate-300 px-3 py-1 text-sm dark:border-slate-600 dark:text-slate-300"
          }
          onClick={toggleUnsureFilter}
        >
          UNSURE only
        </button>
        <select
          data-testid="bank-filter-select"
          className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          value={filter.bank ?? ""}
          onChange={(e) => updateFilter({ bank: e.target.value || undefined })}
          onFocus={() => void refetchBanks()}
        >
          <option value="">All banks</option>
          {banks?.map((bank) => (
            <option key={bank} value={bank}>
              {bank}
            </option>
          ))}
        </select>
        <select
          data-testid="category-filter-select"
          className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          value={filter.category ?? ""}
          onChange={(e) => updateFilter({ category: e.target.value || undefined })}
          onFocus={() => void refetchCategories()}
        >
          <option value="">All categories</option>
          {[...(categories ?? [])]
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((category) => (
              <option key={category.id} value={category.name}>
                {category.name}
              </option>
            ))}
        </select>
        <select
          data-testid="group-by-select"
          className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
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
          className="ml-auto rounded border border-slate-300 px-3 py-1 text-sm dark:border-slate-600 dark:text-slate-300"
          onClick={handleExport}
        >
          Export CSV
        </button>
      </div>

      {isPending && <p>Loading...</p>}

      {data && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-700 dark:text-slate-400">
              <SortableTh
                className="py-2"
                label="Date"
                sortKey="date"
                activeSortKey={filter.sortBy}
                sortDir={filter.sortDir ?? "desc"}
                onSort={handleSort}
              />
              <th>Description</th>
              <SortableTh
                label="Out/In-flow"
                sortKey="amount"
                colSpan={2}
                activeSortKey={filter.sortBy}
                sortDir={filter.sortDir ?? "desc"}
                onSort={handleSort}
              />
              <SortableTh
                label="Bank"
                sortKey="bank"
                activeSortKey={filter.sortBy}
                sortDir={filter.sortDir ?? "desc"}
                onSort={handleSort}
              />
              <SortableTh
                label="Category"
                sortKey="category"
                activeSortKey={filter.sortBy}
                sortDir={filter.sortDir ?? "desc"}
                onSort={handleSort}
              />
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
                        .map((txn, index) => (
                          <TransactionRow key={txn.id} txn={txn} index={index} onCorrected={refetchAfterCorrection} />
                        ))}
                    </Fragment>
                  ))
              : data.items.map((txn, index) => (
                  <TransactionRow key={txn.id} txn={txn} index={index} onCorrected={refetchAfterCorrection} />
                ))}
          </tbody>
        </table>
      )}

      {data && data.items.length === 0 && (
        <p className="text-slate-500 dark:text-slate-400">No matching transactions.</p>
      )}

      {data && (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <button
            disabled={(filter.page ?? 1) <= 1}
            onClick={() => updateFilter({ page: (filter.page ?? 1) - 1 })}
            className="rounded border px-2 py-1 disabled:opacity-40 dark:border-slate-600 dark:text-slate-300"
          >
            Previous
          </button>
          <span>
            Page {data.page} of {Math.max(1, Math.ceil(data.totalCount / data.pageSize))}
          </span>
          <button
            disabled={data.page * data.pageSize >= data.totalCount}
            onClick={() => updateFilter({ page: (filter.page ?? 1) + 1 })}
            className="rounded border px-2 py-1 disabled:opacity-40 dark:border-slate-600 dark:text-slate-300"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
