import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";

import { getBalanceSeries } from "../../api/balances";
import type { BalanceGranularity, SeriesResponse } from "../../api/types";
import { useTheme } from "../../context/ThemeContext";
import { balanceErrorMessage, EXCLUSION_REASONS } from "../../lib/balances";
import {
  buildBalanceLines,
  chartLabels,
  formatAxisTick,
  markerRadius,
  summarizeSeries,
  toChartNumbers,
} from "../../lib/balanceChart";
import { lineMarkStyle } from "../../lib/chartColors";
import { getChartTheme } from "../../lib/chartTheme";
import { formatDay } from "../../lib/duplicates";
import { formatMoney } from "../../lib/money";
import { seriesKey } from "./queries";

const EARLIEST_DATE = "2000-01-01";
const CONTROL = "rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

const GRANULARITY_CHOICES: { value: BalanceGranularity; label: string }[] = [
  { value: "auto", label: "Automatic" },
  { value: "day", label: "Daily" },
  { value: "month", label: "Month-end" },
];

type Range = { from?: string; to?: string };

// Epic 13 (US-13.5, Question 2 = A): the balance over time. It opens on the API's own default (the last 12 months
// ending today: no dates are sent until the owner edits one, and then both are). Every plotted value is the figure the
// lookup would return for that date, drawn from the API's exact strings; a gap stays a gap.
export function BalanceChart({ today }: { today: string | null }) {
  const { theme } = useTheme();
  const [range, setRange] = useState<Range>({});
  const [granularity, setGranularity] = useState<BalanceGranularity>("auto");

  const params = { ...range, granularity };
  const query = useQuery({
    queryKey: seriesKey(params),
    queryFn: () => getBalanceSeries(params),
    placeholderData: keepPreviousData,
    retry: false,
  });

  // A refused range keeps the last chart that was good on screen beneath its sentence.
  const [lastGood, setLastGood] = useState<SeriesResponse | null>(null);
  useEffect(() => {
    if (query.data && !query.isPlaceholderData) setLastGood(query.data);
  }, [query.data, query.isPlaceholderData]);
  const series = query.data ?? lastGood;

  const latest = today ?? undefined;
  const shownFrom = range.from ?? series?.start ?? "";
  const shownTo = range.to ?? series?.end ?? "";

  function changeDate(which: "from" | "to", value: string) {
    if (!value || value < EARLIEST_DATE || (latest && value > latest)) return;
    setRange({
      from: which === "from" ? value : (range.from ?? series?.start),
      to: which === "to" ? value : (range.to ?? series?.end),
    });
  }

  return (
    <section data-testid="balance-chart" className="mb-6">
      <h3 className="mb-2 font-medium">Balance over time</h3>
      <div className="mb-3 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex items-center gap-2">
          From
          <input
            type="date"
            data-testid="series-from"
            min={EARLIEST_DATE}
            max={latest}
            value={shownFrom}
            onChange={(event) => changeDate("from", event.target.value)}
            className={CONTROL}
          />
        </label>
        <label className="flex items-center gap-2">
          To
          <input
            type="date"
            data-testid="series-to"
            min={EARLIEST_DATE}
            max={latest}
            value={shownTo}
            onChange={(event) => changeDate("to", event.target.value)}
            className={CONTROL}
          />
        </label>
        <button
          type="button"
          data-testid="series-reset"
          onClick={() => setRange({})}
          className="min-h-[36px] rounded border border-slate-300 px-3 py-1 dark:border-slate-600"
        >
          Last 12 months
        </button>
        <fieldset className="flex items-center gap-3">
          <legend className="sr-only">Points</legend>
          {GRANULARITY_CHOICES.map((choice) => (
            <label key={choice.value} className="flex items-center gap-1">
              <input
                type="radio"
                name="series-granularity"
                data-testid={`series-granularity-${choice.value}`}
                checked={granularity === choice.value}
                onChange={() => setGranularity(choice.value)}
              />
              {choice.label}
            </label>
          ))}
        </fieldset>
      </div>

      {query.isError && (
        <div data-testid="series-error" role="alert" className="mb-3 text-sm text-red-600 dark:text-red-400">
          {balanceErrorMessage(query.error)}{" "}
          <button type="button" data-testid="series-retry" onClick={() => query.refetch()} className="underline">
            Try again
          </button>
        </div>
      )}

      {!series && !query.isError && (
        <p data-testid="series-loading" className="text-sm text-slate-500 dark:text-slate-400">
          Loading chart&hellip;
        </p>
      )}

      {series && <ChartBody series={series} theme={theme} />}
    </section>
  );
}

function ChartBody({ series, theme }: { series: SeriesResponse; theme: "light" | "dark" }) {
  const chartTheme = getChartTheme<"line">(theme);
  const lines = buildBalanceLines(series, theme);
  const labels = chartLabels(series);
  const summary = summarizeSeries(series);
  const hasGap = lines.some((line) => line.values.some((value) => value === null));
  const base = chartTheme.options;

  const options = {
    ...base,
    interaction: { mode: "index" as const, intersect: false },
    scales: {
      x: { ...base.scales?.x, ticks: { ...base.scales?.x?.ticks, autoSkip: true, maxRotation: 0, maxTicksLimit: 12 } },
      y: { ...base.scales?.y, ticks: { ...base.scales?.y?.ticks, callback: (value: string | number) => formatAxisTick(value) } },
    },
    plugins: {
      ...base.plugins,
      tooltip: {
        callbacks: {
          title: (items: { dataIndex: number }[]) => formatDay(series.points[items[0].dataIndex].date, true),
          label: (item: { datasetIndex: number; dataIndex: number; dataset: { label?: string } }) =>
            `${item.dataset.label}: ${formatMoney(lines[item.datasetIndex].values[item.dataIndex], "SGD")}`,
        },
      },
    },
  };

  const datasets = lines.map((line) => ({
    label: line.label,
    data: toChartNumbers(line.values),
    ...lineMarkStyle(line.color, chartTheme.surfaceColor),
    borderWidth: line.width,
    pointRadius: markerRadius(series.points.length),
    pointHoverRadius: 5,
    tension: 0, // straight segments: a balance changes on the day of a transaction, a curve would invent values
    spanGaps: false,
  }));

  return (
    <div>
      <p data-testid="series-resolved" className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {series.granularity === "day" ? "Showing every day" : "Showing month-end points"}
      </p>
      {series.accounts.length === 0 ? (
        <p data-testid="series-empty" className="text-sm text-slate-500 dark:text-slate-400">
          Enter a balance for at least one account to see the chart.
        </p>
      ) : (
        <div data-testid="series-chart" role="img" aria-label={summary} className="relative h-72 w-full">
          <Line data={{ labels, datasets }} options={options as never} />
        </div>
      )}
      {series.accounts.length > 0 && (
        <p data-testid="series-summary" className="mt-2 text-sm">
          {summary}
        </p>
      )}
      {series.missingAccounts.length > 0 && (
        <p data-testid="series-not-plotted" className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Not plotted: {series.missingAccounts.map((m) => `${m.name} (${EXCLUSION_REASONS[m.reason]})`).join(", ")}
        </p>
      )}
      {hasGap && (
        <p data-testid="series-gap-note" className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          A break in a line means no exchange rate was available for that date.
        </p>
      )}
    </div>
  );
}
