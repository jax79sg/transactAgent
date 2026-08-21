import * as Tabs from "@radix-ui/react-tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, Line } from "react-chartjs-2";

import { getBankBreakdown, getCashFlow, getCategoryTrends } from "../api/dashboards";
import {
  addFromDetectionSuggestion,
  approveMatch,
  bulkImportRecurringPayments,
  createRecurringPayment,
  dismissDetectionSuggestion,
  listDetectionSuggestions,
  listPendingMatches,
  listRecurringPayments,
  rejectMatch,
} from "../api/recurringPayments";
import type { BulkImportRow, DashboardFilterState, RecurringPaymentFrequency, RecurringPaymentStatus } from "../api/types";
import { useTheme } from "../context/ThemeContext";
import { CATEGORICAL_PALETTE, OTHER_LABEL, barMarkStyle, buildCategoricalSeries, lineMarkStyle } from "../lib/chartColors";
import { getChartTheme } from "../lib/chartTheme";

function defaultDateRange(): DashboardFilterState {
  const today = new Date();
  const sixMonthsAgo = new Date(today.getFullYear(), today.getMonth() - 5, 1);
  return {
    dateFrom: sixMonthsAgo.toISOString().slice(0, 10),
    dateTo: today.toISOString().slice(0, 10),
  };
}

function DisclosureBanner({ approximateCount, excludedCount }: { approximateCount: number; excludedCount: number }) {
  if (approximateCount === 0 && excludedCount === 0) return null;
  return (
    <p className="mb-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
      {approximateCount > 0 && `${approximateCount} transaction(s) use an approximate exchange rate. `}
      {excludedCount > 0 && `${excludedCount} transaction(s) excluded (no exchange rate available).`}
    </p>
  );
}

function DateRangeFilter({
  filter,
  onChange,
}: {
  filter: DashboardFilterState;
  onChange: (filter: DashboardFilterState) => void;
}) {
  return (
    <div className="mb-4 flex gap-3 text-sm">
      <label className="flex items-center gap-2">
        From
        <input
          type="date"
          value={filter.dateFrom}
          onChange={(e) => onChange({ ...filter, dateFrom: e.target.value })}
          className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
      </label>
      <label className="flex items-center gap-2">
        To
        <input
          type="date"
          value={filter.dateTo}
          onChange={(e) => onChange({ ...filter, dateTo: e.target.value })}
          className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
      </label>
    </div>
  );
}

function monthBounds(month: string): { dateFrom: string; dateTo: string } {
  const [year, monthIndex] = month.split("-").map(Number);
  const from = new Date(year, monthIndex - 1, 1);
  const to = new Date(year, monthIndex, 0);
  return { dateFrom: from.toISOString().slice(0, 10), dateTo: to.toISOString().slice(0, 10) };
}

function CategoryTrendsTab({ filter }: { filter: DashboardFilterState }) {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const { data, isPending } = useQuery({
    queryKey: ["dashboards", "category-trends", filter],
    queryFn: () => getCategoryTrends(filter),
  });

  if (isPending) return <p>Loading...</p>;
  if (!data) return null;

  const months = Array.from(new Set(data.series.map((p) => p.month))).sort();
  const series = buildCategoricalSeries(
    data.series,
    months,
    (p) => p.month,
    (p) => p.category,
    (p) => Number(p.totalSgd),
  );
  const datasets = series.map((s) => ({ label: s.label, data: s.data, ...barMarkStyle(s.color) }));

  return (
    <div>
      <DisclosureBanner {...data.disclosure} />
      <Bar
        data={{ labels: months, datasets }}
        options={{
          ...getChartTheme<"bar">(theme).options,
          onClick: (_evt, elements) => {
            if (elements.length === 0) return;
            const { datasetIndex, index } = elements[0];
            const category = series[datasetIndex].label;
            if (category === OTHER_LABEL) return; // no single category to filter by
            const { dateFrom, dateTo } = monthBounds(months[index]);
            navigate(`/transactions?category=${encodeURIComponent(category)}&dateFrom=${dateFrom}&dateTo=${dateTo}`);
          },
        }}
      />
    </div>
  );
}

function CashFlowTab({ filter }: { filter: DashboardFilterState }) {
  const { theme } = useTheme();
  const { data, isPending } = useQuery({
    queryKey: ["dashboards", "cash-flow", filter],
    queryFn: () => getCashFlow(filter),
  });

  if (isPending) return <p>Loading...</p>;
  if (!data) return null;

  const chartTheme = getChartTheme<"line">(theme);

  return (
    <div>
      <DisclosureBanner {...data.disclosure} />
      <Line
        data={{
          labels: data.series.map((p) => p.month),
          datasets: [
            {
              label: "Income",
              data: data.series.map((p) => Number(p.incomeSgd)),
              ...lineMarkStyle(CATEGORICAL_PALETTE[0], chartTheme.surfaceColor),
            },
            {
              label: "Expenses",
              data: data.series.map((p) => Number(p.expenseSgd)),
              ...lineMarkStyle(CATEGORICAL_PALETTE[1], chartTheme.surfaceColor),
            },
            {
              label: "Net",
              data: data.series.map((p) => Number(p.netSgd)),
              ...lineMarkStyle(CATEGORICAL_PALETTE[2], chartTheme.surfaceColor),
            },
          ],
        }}
        options={chartTheme.options}
      />
    </div>
  );
}

function BankBreakdownTab({ filter }: { filter: DashboardFilterState }) {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const { data, isPending } = useQuery({
    queryKey: ["dashboards", "bank-breakdown", filter],
    queryFn: () => getBankBreakdown(filter),
  });

  if (isPending) return <p>Loading...</p>;
  if (!data) return null;

  const months = Array.from(new Set(data.series.map((p) => p.month))).sort();
  const series = buildCategoricalSeries(
    data.series,
    months,
    (p) => p.month,
    (p) => p.bankName,
    (p) => Number(p.totalSgd),
  );
  const datasets = series.map((s) => ({ label: s.label, data: s.data, ...barMarkStyle(s.color) }));

  return (
    <div>
      <DisclosureBanner {...data.disclosure} />
      <Bar
        data={{ labels: months, datasets }}
        options={{
          ...getChartTheme<"bar">(theme).options,
          onClick: (_evt, elements) => {
            if (elements.length === 0) return;
            const { datasetIndex, index } = elements[0];
            const bank = series[datasetIndex].label;
            if (bank === OTHER_LABEL) return; // no single bank to filter by
            const { dateFrom, dateTo } = monthBounds(months[index]);
            navigate(`/transactions?bank=${encodeURIComponent(bank)}&dateFrom=${dateFrom}&dateTo=${dateTo}`);
          },
        }}
      />
    </div>
  );
}

const STATUS_LABELS: Record<RecurringPaymentStatus, string> = {
  due_soon: "Due soon",
  overdue: "Overdue",
  pending_review: "Pending review",
  paid: "Paid",
};

const STATUS_STYLES: Record<RecurringPaymentStatus, string> = {
  due_soon: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  overdue: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  pending_review: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  paid: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
};

function StatusBadge({ status }: { status: RecurringPaymentStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`} data-testid={`status-badge-${status}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

/** Parses pasted bulk-import rows: "Name, Amount, Frequency, DueDay" (monthly) or
 * "Name, Amount, Frequency, DueMonth, DueDay" (annual), one per line. */
function parseBulkImportText(text: string): BulkImportRow[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const parts = line.split(",").map((p) => p.trim());
      const [name, amount, frequencyRaw, ...rest] = parts;
      const frequency = frequencyRaw?.toLowerCase() as RecurringPaymentFrequency;
      if (frequency === "annual" && rest.length >= 2) {
        return { name, amount, frequency, dueMonth: rest[0], dueDay: rest[1] };
      }
      return { name, amount, frequency, dueDay: rest[0] };
    });
}

function RecurringPaymentsTab() {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newFrequency, setNewFrequency] = useState<RecurringPaymentFrequency>("monthly");
  const [newDueMonth, setNewDueMonth] = useState("");
  const [newDueDay, setNewDueDay] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [bulkResult, setBulkResult] = useState<{ createdCount: number; failed: { row: number; reason: string }[] } | null>(null);

  const { data: payments } = useQuery({ queryKey: ["recurringPayments", "list"], queryFn: listRecurringPayments });
  const { data: matches } = useQuery({ queryKey: ["recurringPayments", "matches"], queryFn: listPendingMatches });
  const { data: suggestions } = useQuery({
    queryKey: ["recurringPayments", "suggestions"],
    queryFn: listDetectionSuggestions,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["recurringPayments"] });
  };

  const createMutation = useMutation({
    mutationFn: createRecurringPayment,
    onSuccess: () => {
      setNewName("");
      setNewAmount("");
      setNewDueMonth("");
      setNewDueDay("");
      invalidateAll();
    },
  });

  const bulkImportMutation = useMutation({
    mutationFn: bulkImportRecurringPayments,
    onSuccess: (result) => {
      setBulkResult({ createdCount: result.created.length, failed: result.failed });
      setBulkText("");
      invalidateAll();
    },
  });

  const approveMutation = useMutation({ mutationFn: approveMatch, onSuccess: invalidateAll });
  const rejectMutation = useMutation({ mutationFn: rejectMatch, onSuccess: invalidateAll });
  const addSuggestionMutation = useMutation({ mutationFn: addFromDetectionSuggestion, onSuccess: invalidateAll });
  const dismissSuggestionMutation = useMutation({ mutationFn: dismissDetectionSuggestion, onSuccess: invalidateAll });

  const dueSoonCount = payments?.filter((p) => p.status === "due_soon").length ?? 0;
  const overdueCount = payments?.filter((p) => p.status === "overdue").length ?? 0;

  return (
    <div>
      <div className="mb-4 flex gap-4 text-sm">
        <span data-testid="summary-due-soon">Due soon: {dueSoonCount}</span>
        <span data-testid="summary-overdue">Overdue: {overdueCount}</span>
        <span data-testid="summary-pending">Pending review: {matches?.length ?? 0}</span>
        <span data-testid="summary-suggestions">New suggestions: {suggestions?.length ?? 0}</span>
      </div>

      <section className="mb-6">
        <h2 className="mb-2 font-medium">Recurring Payments</h2>
        {(payments?.length ?? 0) === 0 ? (
          <p data-testid="recurring-payments-empty-state" className="text-sm text-slate-500 dark:text-slate-400">
            No recurring payments yet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th>Name</th>
                <th>Amount</th>
                <th>Due</th>
                <th>Set aside/mo</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {payments!.map((payment) => (
                <tr
                  key={payment.id}
                  data-testid={`recurring-payment-row-${payment.id}`}
                  className="border-b border-slate-100 dark:border-slate-800"
                >
                  <td>{payment.name}</td>
                  <td>{payment.expectedAmount}</td>
                  <td>
                    {payment.frequency === "annual" ? `${payment.dueMonth}/${payment.dueDay}` : `day ${payment.dueDay}`}
                  </td>
                  <td>{payment.monthlySetAside ?? "-"}</td>
                  <td>
                    <StatusBadge status={payment.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form
          className="mt-3 flex flex-wrap items-end gap-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate({
              name: newName,
              expectedAmount: newAmount,
              frequency: newFrequency,
              dueMonth: newFrequency === "annual" ? Number(newDueMonth) : null,
              dueDay: Number(newDueDay),
            });
          }}
        >
          <input
            data-testid="new-recurring-payment-name"
            placeholder="Name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <input
            data-testid="new-recurring-payment-amount"
            placeholder="Amount"
            value={newAmount}
            onChange={(e) => setNewAmount(e.target.value)}
            className="w-24 rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <select
            data-testid="new-recurring-payment-frequency"
            value={newFrequency}
            onChange={(e) => setNewFrequency(e.target.value as RecurringPaymentFrequency)}
            className="rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="monthly">Monthly</option>
            <option value="annual">Annual</option>
          </select>
          {newFrequency === "annual" && (
            <input
              data-testid="new-recurring-payment-due-month"
              placeholder="Due month"
              value={newDueMonth}
              onChange={(e) => setNewDueMonth(e.target.value)}
              className="w-24 rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
          )}
          <input
            data-testid="new-recurring-payment-due-day"
            placeholder="Due day"
            value={newDueDay}
            onChange={(e) => setNewDueDay(e.target.value)}
            className="w-24 rounded border px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            type="submit"
            data-testid="add-recurring-payment-button"
            className="rounded bg-slate-900 px-3 py-1 text-white dark:bg-slate-100 dark:text-slate-900"
          >
            Add
          </button>
        </form>
        {createMutation.isError && (
          <p data-testid="add-recurring-payment-error" className="mt-1 text-xs text-red-600 dark:text-red-400">
            Couldn't add that recurring payment -- check the values and try again.
          </p>
        )}

        <div className="mt-4">
          <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
            Bulk import (one per line: Name, Amount, Frequency, DueDay -- or DueMonth, DueDay for annual)
          </label>
          <textarea
            data-testid="bulk-import-textarea"
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            rows={3}
            className="w-full rounded border px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            data-testid="bulk-import-button"
            onClick={() => bulkImportMutation.mutate(parseBulkImportText(bulkText))}
            disabled={bulkText.trim().length === 0}
            className="mt-1 rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-50 dark:border-slate-600 dark:text-slate-300"
          >
            Import
          </button>
          {bulkResult && (
            <p data-testid="bulk-import-result" className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              Added {bulkResult.createdCount}. {bulkResult.failed.length > 0 && `${bulkResult.failed.length} row(s) failed.`}
            </p>
          )}
        </div>
      </section>

      <section className="mb-6">
        <h2 className="mb-2 font-medium">Pending Matches</h2>
        {(matches?.length ?? 0) === 0 ? (
          <p data-testid="pending-matches-empty-state" className="text-sm text-slate-500 dark:text-slate-400">
            Nothing waiting for review.
          </p>
        ) : (
          <ul className="text-sm">
            {matches!.map((match) => (
              <li
                key={match.id}
                data-testid={`pending-match-row-${match.id}`}
                className="flex items-center gap-3 border-b border-slate-100 py-1 dark:border-slate-800"
              >
                <span className="flex-1">
                  {match.recurringPayment.name} — {match.transaction.description} ({match.amountAtMatch})
                </span>
                <button
                  data-testid={`approve-match-${match.id}`}
                  onClick={() => approveMutation.mutate(match.id)}
                  className="text-slate-900 underline dark:text-slate-100"
                >
                  Approve
                </button>
                <button
                  data-testid={`reject-match-${match.id}`}
                  onClick={() => rejectMutation.mutate(match.id)}
                  className="text-slate-500 underline dark:text-slate-400"
                >
                  Reject
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-medium">Detected Recurring Charges</h2>
        {(suggestions?.length ?? 0) === 0 ? (
          <p data-testid="suggestions-empty-state" className="text-sm text-slate-500 dark:text-slate-400">
            Nothing new detected.
          </p>
        ) : (
          <ul className="text-sm">
            {suggestions!.map((suggestion) => (
              <li
                key={suggestion.id}
                data-testid={`suggestion-row-${suggestion.id}`}
                className="flex items-center gap-3 border-b border-slate-100 py-1 dark:border-slate-800"
              >
                <span className="flex-1">
                  {suggestion.descriptionPattern} — {suggestion.suggestedAmount} ({suggestion.occurrenceCount}x)
                </span>
                <button
                  data-testid={`add-suggestion-${suggestion.id}`}
                  onClick={() => addSuggestionMutation.mutate(suggestion.id)}
                  className="text-slate-900 underline dark:text-slate-100"
                >
                  Add
                </button>
                <button
                  data-testid={`dismiss-suggestion-${suggestion.id}`}
                  onClick={() => dismissSuggestionMutation.mutate(suggestion.id)}
                  className="text-slate-500 underline dark:text-slate-400"
                >
                  Dismiss
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function DashboardPage() {
  const [filter, setFilter] = useState<DashboardFilterState>(defaultDateRange);
  const dashboardFilter = useMemo(() => filter, [filter]);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Dashboard</h1>
      <DateRangeFilter filter={dashboardFilter} onChange={setFilter} />
      <Tabs.Root defaultValue="category-trends">
        <Tabs.List className="mb-4 flex gap-4 border-b border-slate-200 dark:border-slate-700">
          <Tabs.Trigger value="category-trends" className="px-2 py-2 data-[state=active]:font-semibold">
            Category Trends
          </Tabs.Trigger>
          <Tabs.Trigger value="cash-flow" className="px-2 py-2 data-[state=active]:font-semibold">
            Cash Flow
          </Tabs.Trigger>
          <Tabs.Trigger value="bank-breakdown" className="px-2 py-2 data-[state=active]:font-semibold">
            Bank Breakdown
          </Tabs.Trigger>
          <Tabs.Trigger value="recurring-payments" className="px-2 py-2 data-[state=active]:font-semibold">
            Recurring Payments
          </Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="category-trends">
          <CategoryTrendsTab filter={dashboardFilter} />
        </Tabs.Content>
        <Tabs.Content value="cash-flow">
          <CashFlowTab filter={dashboardFilter} />
        </Tabs.Content>
        <Tabs.Content value="bank-breakdown">
          <BankBreakdownTab filter={dashboardFilter} />
        </Tabs.Content>
        <Tabs.Content value="recurring-payments">
          <RecurringPaymentsTab />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
