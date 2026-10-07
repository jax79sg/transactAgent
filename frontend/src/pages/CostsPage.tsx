import { useQuery } from "@tanstack/react-query";
import type { ChartOptions } from "chart.js";
import { useMemo, useState } from "react";
import { Bar } from "react-chartjs-2";

import { getCosts } from "../api/costs";
import type { CostFilterState, CostGranularity, CostGroupBy, CostsResponse } from "../api/types";
import { SortableTh } from "../components/SortableTh";
import { useTheme } from "../context/ThemeContext";
import { barMarkStyle } from "../lib/chartColors";
import { getChartTheme } from "../lib/chartTheme";
import {
  type PeriodRow,
  type SortDirection,
  axisLabel,
  buildCostDatasets,
  buildPeriodRows,
  groupLabel,
  periodLabel,
  sortRows,
} from "../lib/costsChart";
import { formatCount, formatUsd } from "../lib/formatUsd";

/** A date as the viewer's own calendar day (toISOString would give the UTC day, a day behind in the early morning
 * east of Greenwich). */
function localIsoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function defaultRange(): { dateFrom: string; dateTo: string } {
  const today = new Date();
  const thirtyDaysInclusive = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29);
  return { dateFrom: localIsoDate(thirtyDaysInclusive), dateTo: localIsoDate(today) };
}

function viewerTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

const GRANULARITY_LABELS: Record<CostGranularity, string> = { day: "Day", week: "Week", month: "Month" };
const GROUP_BY_LABELS: Record<CostGroupBy, string> = { none: "Nothing", purpose: "Purpose", model: "Model" };

const inputClass =
  "rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function SummaryTile({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="rounded border border-slate-200 p-3 dark:border-slate-700">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div data-testid={testId} className="text-xl font-semibold">
        {value}
      </div>
    </div>
  );
}

function CostChart({ response }: { response: CostsResponse }) {
  const { theme } = useTheme();
  const chartTheme = getChartTheme<"bar">(theme);
  const datasets = buildCostDatasets(response);
  const stacked = datasets.length > 1;
  const baseScales = chartTheme.options.scales;

  const options = {
    ...chartTheme.options,
    scales: {
      x: { ...baseScales?.x, stacked },
      y: {
        ...baseScales?.y,
        stacked,
        beginAtZero: true,
        ticks: { ...baseScales?.y?.ticks, callback: (value: string | number) => formatUsd(Number(value)) },
      },
    },
    plugins: {
      legend: { ...chartTheme.options.plugins?.legend, display: stacked },
      tooltip: {
        callbacks: {
          title: (items: { dataIndex: number }[]) => periodLabel(response.periods[items[0].dataIndex], response.granularity),
          label: (item: { dataset: { label?: string }; parsed: { y: number | null } }) =>
            `${item.dataset.label}: ${formatUsd(item.parsed.y ?? 0)}`,
          footer: (items: { parsed: { y: number | null } }[]) =>
            items.length > 1 ? `Total: ${formatUsd(items.reduce((sum, i) => sum + (i.parsed.y ?? 0), 0))}` : "",
        },
      },
    },
  } as ChartOptions<"bar">;

  return (
    <div
      data-testid="costs-chart-frame"
      role="img"
      aria-label={`Model cost per ${response.granularity}, ${formatUsd(response.totals.costUsd)} in total. The table below has the same figures.`}
      className="relative h-72 w-full"
    >
      <Bar
        data={{
          labels: response.periods.map((p) => axisLabel(p, response.granularity)),
          datasets: datasets.map((d) => ({
            label: d.label,
            data: d.data,
            // Stacked segments sit on each other, so they get a 2px surface gap instead of rounded ends; a single
            // series keeps the app's usual rounded bar.
            ...(stacked
              ? { backgroundColor: d.color, borderColor: chartTheme.surfaceColor, borderWidth: 2, maxBarThickness: 24 }
              : barMarkStyle(d.color)),
          })),
        }}
        options={options}
      />
    </div>
  );
}

type PeriodSortKey = "period" | "costUsd" | "calls" | "inputTokens" | "outputTokens";
type GroupSortKey = "group" | "costUsd" | "share" | "calls" | "inputTokens" | "outputTokens";

function PeriodTable({ response }: { response: CostsResponse }) {
  const [sort, setSort] = useState<{ key: PeriodSortKey; dir: SortDirection }>({ key: "period", dir: "desc" });
  const rows = useMemo(
    () => sortRows<PeriodRow, PeriodSortKey>(buildPeriodRows(response), sort.key, sort.dir, "period"),
    [response, sort],
  );
  const onSort = (key: PeriodSortKey, dir: SortDirection) => setSort({ key, dir });
  const header = (label: string, key: PeriodSortKey, className = "text-right") => (
    <SortableTh<PeriodSortKey>
      label={label}
      sortKey={key}
      activeSortKey={sort.key}
      sortDir={sort.dir}
      onSort={onSort}
      className={`px-3 py-2 ${className}`}
      testId={`costs-period-sort-${key}`}
    />
  );

  return (
    <div className="overflow-x-auto">
      <table data-testid="costs-period-table" className="w-full text-sm">
        <caption className="mb-1 text-left font-medium">By {response.granularity}</caption>
        <thead className="text-left text-slate-500 dark:text-slate-400">
          <tr>
            {header("Period", "period", "text-left")}
            {header("Cost (USD)", "costUsd")}
            {header("Calls", "calls")}
            {header("Input tokens", "inputTokens")}
            {header("Output tokens", "outputTokens")}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.period} className="border-t border-slate-200 dark:border-slate-700">
              <td className="px-3 py-2">{periodLabel(row.period, response.granularity)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatUsd(row.costUsd)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.calls)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.inputTokens)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.outputTokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupTable({ response }: { response: CostsResponse }) {
  const [sort, setSort] = useState<{ key: GroupSortKey; dir: SortDirection }>({ key: "costUsd", dir: "desc" });
  const total = Number(response.totals.costUsd);
  const rows = useMemo(
    () =>
      sortRows(
        response.groups.map((g) => ({
          group: groupLabel(g.group, response.groupBy),
          costUsd: Number(g.costUsd),
          share: total > 0 ? Number(g.costUsd) / total : 0,
          calls: g.calls,
          inputTokens: g.inputTokens,
          outputTokens: g.outputTokens,
        })),
        sort.key,
        sort.dir,
        "group",
      ),
    [response, sort, total],
  );
  const onSort = (key: GroupSortKey, dir: SortDirection) => setSort({ key, dir });
  const header = (label: string, key: GroupSortKey, className = "text-right") => (
    <SortableTh<GroupSortKey>
      label={label}
      sortKey={key}
      activeSortKey={sort.key}
      sortDir={sort.dir}
      onSort={onSort}
      className={`px-3 py-2 ${className}`}
      testId={`costs-group-sort-${key}`}
    />
  );

  return (
    <div className="overflow-x-auto">
      <table data-testid="costs-group-table" className="w-full text-sm">
        <caption className="mb-1 text-left font-medium">By {GROUP_BY_LABELS[response.groupBy].toLowerCase()}</caption>
        <thead className="text-left text-slate-500 dark:text-slate-400">
          <tr>
            {header(GROUP_BY_LABELS[response.groupBy], "group", "text-left")}
            {header("Cost (USD)", "costUsd")}
            {header("Share", "share")}
            {header("Calls", "calls")}
            {header("Input tokens", "inputTokens")}
            {header("Output tokens", "outputTokens")}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.group} className="border-t border-slate-200 dark:border-slate-700">
              <td className="px-3 py-2">{row.group}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatUsd(row.costUsd)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{(row.share * 100).toFixed(1)}%</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.calls)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.inputTokens)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatCount(row.outputTokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CostsResult({ response }: { response: CostsResponse }) {
  const { totals } = response;

  if (totals.calls === 0) {
    return (
      <p data-testid="costs-empty" className="rounded bg-slate-100 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
        No model calls were recorded in this range. Spending is recorded from the moment this page was introduced;
        calls made before then are not included.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryTile label="Total cost (USD)" value={formatUsd(totals.costUsd)} testId="costs-total" />
        <SummaryTile label="Calls" value={formatCount(totals.calls)} testId="costs-calls" />
        <SummaryTile label="Input tokens" value={formatCount(totals.inputTokens)} testId="costs-input-tokens" />
        <SummaryTile label="Output tokens" value={formatCount(totals.outputTokens)} testId="costs-output-tokens" />
      </div>
      {totals.estimatedCalls > 0 && (
        <p
          data-testid="costs-estimate-note"
          className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          {formatCount(totals.estimatedCalls)} of these {formatCount(totals.calls)} calls (embeddings) have estimated
          token counts, because Google reports none for them, so their cost is an estimate.
        </p>
      )}
      <CostChart response={response} />
      <PeriodTable response={response} />
      {response.groupBy !== "none" && <GroupTable response={response} />}
    </div>
  );
}

export function CostsPage() {
  const [range, setRange] = useState(defaultRange);
  const [granularity, setGranularity] = useState<CostGranularity>("day");
  const [groupBy, setGroupBy] = useState<CostGroupBy>("purpose");
  const [timezone] = useState(viewerTimeZone);

  const filter: CostFilterState = { ...range, granularity, groupBy, timezone };
  const rangeIsValid = range.dateFrom !== "" && range.dateTo !== "" && range.dateFrom <= range.dateTo;
  const { data, isPending, isError } = useQuery({
    queryKey: ["costs", filter],
    queryFn: () => getCosts(filter),
    enabled: rangeIsValid,
  });

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">Costs</h1>
      <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
        What the app has spent on Google&apos;s Gemini models, in US dollars: statement extraction, categorization,
        embeddings and Ask AI. Each call is priced from its token count and the prices in Settings. Calls to local
        models cost nothing and are not counted.
      </p>

      <div className="mb-4 flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-2">
          From
          <input
            data-testid="costs-from"
            type="date"
            value={range.dateFrom}
            onChange={(e) => setRange({ ...range, dateFrom: e.target.value })}
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-2">
          To
          <input
            data-testid="costs-to"
            type="date"
            value={range.dateTo}
            onChange={(e) => setRange({ ...range, dateTo: e.target.value })}
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-2">
          Show by
          <select
            data-testid="costs-granularity"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as CostGranularity)}
            className={inputClass}
          >
            {(Object.keys(GRANULARITY_LABELS) as CostGranularity[]).map((g) => (
              <option key={g} value={g}>
                {GRANULARITY_LABELS[g]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Group by
          <select
            data-testid="costs-group-by"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as CostGroupBy)}
            className={inputClass}
          >
            {(Object.keys(GROUP_BY_LABELS) as CostGroupBy[]).map((g) => (
              <option key={g} value={g}>
                {GROUP_BY_LABELS[g]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!rangeIsValid && (
        <p data-testid="costs-range-error" className="text-sm text-red-600 dark:text-red-400">
          Choose a start date that is not after the end date.
        </p>
      )}
      {rangeIsValid && isPending && <p>Loading...</p>}
      {rangeIsValid && isError && (
        <p data-testid="costs-error" className="text-sm text-red-600 dark:text-red-400">
          The costs could not be loaded. Try again in a moment.
        </p>
      )}
      {rangeIsValid && data && <CostsResult response={data} />}
    </div>
  );
}
