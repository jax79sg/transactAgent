import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, Line } from "react-chartjs-2";

import { getBankBreakdown, getCashFlow, getCategoryTrends } from "../api/dashboards";
import type { DashboardFilterState } from "../api/types";
import { CATEGORICAL_PALETTE, OTHER_LABEL, barMarkStyle, buildCategoricalSeries, lineMarkStyle } from "../lib/chartColors";

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
    <p className="mb-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
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
          className="rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <label className="flex items-center gap-2">
        To
        <input
          type="date"
          value={filter.dateTo}
          onChange={(e) => onChange({ ...filter, dateTo: e.target.value })}
          className="rounded border border-slate-300 px-2 py-1"
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
  const { data, isPending } = useQuery({
    queryKey: ["dashboards", "cash-flow", filter],
    queryFn: () => getCashFlow(filter),
  });

  if (isPending) return <p>Loading...</p>;
  if (!data) return null;

  return (
    <div>
      <DisclosureBanner {...data.disclosure} />
      <Line
        data={{
          labels: data.series.map((p) => p.month),
          datasets: [
            { label: "Income", data: data.series.map((p) => Number(p.incomeSgd)), ...lineMarkStyle(CATEGORICAL_PALETTE[0]) },
            { label: "Expenses", data: data.series.map((p) => Number(p.expenseSgd)), ...lineMarkStyle(CATEGORICAL_PALETTE[1]) },
            { label: "Net", data: data.series.map((p) => Number(p.netSgd)), ...lineMarkStyle(CATEGORICAL_PALETTE[2]) },
          ],
        }}
      />
    </div>
  );
}

function BankBreakdownTab({ filter }: { filter: DashboardFilterState }) {
  const navigate = useNavigate();
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

export function DashboardPage() {
  const [filter, setFilter] = useState<DashboardFilterState>(defaultDateRange);
  const dashboardFilter = useMemo(() => filter, [filter]);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Dashboard</h1>
      <DateRangeFilter filter={dashboardFilter} onChange={setFilter} />
      <Tabs.Root defaultValue="category-trends">
        <Tabs.List className="mb-4 flex gap-4 border-b border-slate-200">
          <Tabs.Trigger value="category-trends" className="px-2 py-2 data-[state=active]:font-semibold">
            Category Trends
          </Tabs.Trigger>
          <Tabs.Trigger value="cash-flow" className="px-2 py-2 data-[state=active]:font-semibold">
            Cash Flow
          </Tabs.Trigger>
          <Tabs.Trigger value="bank-breakdown" className="px-2 py-2 data-[state=active]:font-semibold">
            Bank Breakdown
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
      </Tabs.Root>
    </div>
  );
}
