import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as costsApi from "../src/api/costs";
import type { CostFigures, CostPoint, CostsResponse } from "../src/api/types";
import { ThemeProvider } from "../src/context/ThemeContext";
import { CATEGORICAL_PALETTE } from "../src/lib/chartColors";
import { CostsPage } from "../src/pages/CostsPage";

vi.mock("../src/api/costs");

// The chart is drawn on a canvas jsdom does not have; what matters here is what the page hands it.
interface CapturedChart {
  data: { labels: string[]; datasets: Record<string, unknown>[] };
  options: {
    scales: { x: { stacked: boolean }; y: { stacked: boolean; ticks: { callback: (value: string | number) => string } } };
    plugins: {
      legend: { display: boolean };
      tooltip: {
        callbacks: {
          title: (items: { dataIndex: number }[]) => string;
          label: (item: { dataset: { label?: string }; parsed: { y: number | null } }) => string;
          footer: (items: { parsed: { y: number | null } }[]) => string;
        };
      };
    };
  };
}
let lastChart: CapturedChart | null = null;
vi.mock("react-chartjs-2", () => ({
  Bar: (props: { data: unknown; options: unknown }) => {
    lastChart = props as unknown as CapturedChart;
    return <div data-testid="costs-chart" />;
  },
}));

const NONE: CostFigures = { costUsd: "0", inputTokens: 0, outputTokens: 0, calls: 0, estimatedCalls: 0 };

function point(period: string, group: string, costUsd: string, calls: number, inputTokens: number, outputTokens: number, estimatedCalls = 0): CostPoint {
  return { period, group, costUsd, calls, inputTokens, outputTokens, estimatedCalls };
}

function makeResponse(overrides: Partial<CostsResponse> = {}): CostsResponse {
  return {
    currency: "USD",
    dateFrom: "2026-09-08",
    dateTo: "2026-10-07",
    granularity: "day",
    groupBy: "purpose",
    timezone: "Asia/Singapore",
    periods: ["2026-10-05", "2026-10-06", "2026-10-07"],
    totals: { costUsd: "0.65000000", inputTokens: 5000, outputTokens: 700, calls: 12, estimatedCalls: 0 },
    series: [
      point("2026-10-05", "categorization", "0.40000000", 8, 3000, 400),
      point("2026-10-05", "ask_ai", "0.10000000", 2, 1000, 200),
      point("2026-10-07", "categorization", "0.15000000", 2, 1000, 100),
    ],
    groups: [
      { group: "categorization", costUsd: "0.55000000", inputTokens: 4000, outputTokens: 500, calls: 10, estimatedCalls: 0 },
      { group: "ask_ai", costUsd: "0.10000000", inputTokens: 1000, outputTokens: 200, calls: 2, estimatedCalls: 0 },
    ],
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter>
          <CostsPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function rowsOf(testId: string): string[][] {
  const table = screen.getByTestId(testId);
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent ?? ""));
}

beforeEach(() => {
  lastChart = null;
  vi.spyOn(costsApi, "getCosts").mockResolvedValue(makeResponse());
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("CostsPage request", () => {
  // The test machine's own zone must not decide the outcome: pin the process to Singapore (UTC+8), where the local
  // date and the UTC date differ for eight hours of every day, and put it back afterwards.
  beforeEach(() => {
    vi.stubEnv("TZ", "Asia/Singapore");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("asks for the last 30 days by day, grouped by purpose, in the viewer's own time zone", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 9, 7, 9, 30) }); // 7 Oct 2026, 09:30 in Singapore
    renderPage();

    await waitFor(() => expect(costsApi.getCosts).toHaveBeenCalled());
    expect(costsApi.getCosts).toHaveBeenCalledWith({
      dateFrom: "2026-09-08", // 30 calendar days including today
      dateTo: "2026-10-07",
      granularity: "day",
      groupBy: "purpose",
      timezone: "Asia/Singapore",
    });
  });

  it("uses today's local date even just after midnight, when the UTC date is still yesterday", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 9, 7, 0, 30) }); // 00:30 on 7 Oct in Singapore = 6 Oct in UTC
    renderPage();

    await waitFor(() => expect(costsApi.getCosts).toHaveBeenCalled());
    const filter = vi.mocked(costsApi.getCosts).mock.calls[0][0];
    expect(new Date(2026, 9, 7, 0, 30).toISOString().slice(0, 10)).toBe("2026-10-06"); // the trap this guards against
    expect([filter.dateFrom, filter.dateTo]).toEqual(["2026-09-08", "2026-10-07"]);
  });

  it("asks again with the new choice when the granularity, the grouping or a date is changed", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("costs-total");

    await user.selectOptions(screen.getByTestId("costs-granularity"), "week");
    await waitFor(() => expect(vi.mocked(costsApi.getCosts).mock.lastCall![0].granularity).toBe("week"));

    await user.selectOptions(screen.getByTestId("costs-group-by"), "model");
    await waitFor(() => expect(vi.mocked(costsApi.getCosts).mock.lastCall![0].groupBy).toBe("model"));

    await user.clear(screen.getByTestId("costs-from"));
    await user.type(screen.getByTestId("costs-from"), "2026-10-01");
    await waitFor(() => expect(vi.mocked(costsApi.getCosts).mock.lastCall![0].dateFrom).toBe("2026-10-01"));
  });

  it("does not ask at all, and says why, when the start date is after the end date", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("costs-total");
    const callsBefore = vi.mocked(costsApi.getCosts).mock.calls.length;

    await user.clear(screen.getByTestId("costs-to"));
    await user.type(screen.getByTestId("costs-to"), "2020-01-01");

    expect(await screen.findByTestId("costs-range-error")).toBeInTheDocument();
    expect(vi.mocked(costsApi.getCosts).mock.calls.length).toBe(callsBefore);
    expect(screen.queryByTestId("costs-total")).not.toBeInTheDocument();
  });
});

describe("CostsPage result", () => {
  it("shows the totals in US dollars with the calls and tokens", async () => {
    renderPage();

    expect(await screen.findByTestId("costs-total")).toHaveTextContent("$0.6500");
    expect(screen.getByTestId("costs-calls")).toHaveTextContent("12");
    expect(screen.getByTestId("costs-input-tokens")).toHaveTextContent("5,000");
    expect(screen.getByTestId("costs-output-tokens")).toHaveTextContent("700");
  });

  it("lists the days that had spend, newest first, with their own figures", async () => {
    renderPage();
    await screen.findByTestId("costs-period-table");

    expect(rowsOf("costs-period-table")).toEqual([
      ["Wed 7 Oct 2026", "$0.1500", "2", "1,000", "100"],
      ["Mon 5 Oct 2026", "$0.5000", "10", "4,000", "600"],
    ]);
  });

  it("gives the chart every day of the range, zero where nothing was spent, one bar series per purpose", async () => {
    renderPage();
    await screen.findByTestId("costs-chart");

    expect(lastChart!.data.labels).toEqual(["5 Oct", "6 Oct", "7 Oct"]);
    const [categorization, askAi] = lastChart!.data.datasets;
    expect([categorization.label, categorization.data]).toEqual(["Categorization", [0.4, 0, 0.15]]);
    expect([askAi.label, askAi.data]).toEqual(["Ask AI", [0.1, 0, 0]]);
    expect([categorization.backgroundColor, askAi.backgroundColor]).toEqual([CATEGORICAL_PALETTE[1], CATEGORICAL_PALETTE[3]]);
  });

  it("stacks several groups with a legend and a surface gap, and says the chart has a table", async () => {
    renderPage();
    await screen.findByTestId("costs-chart");

    expect(lastChart!.options.scales.x.stacked).toBe(true);
    expect(lastChart!.options.scales.y.stacked).toBe(true);
    expect(lastChart!.options.plugins.legend.display).toBe(true);
    expect(lastChart!.data.datasets[0].borderWidth).toBe(2);
    expect(screen.getByTestId("costs-chart-frame")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("costs-chart-frame").getAttribute("aria-label")).toMatch(/\$0\.6500 in total.*table below/);
  });

  it("draws a single, unstacked series without a legend when nothing is grouped", async () => {
    vi.mocked(costsApi.getCosts).mockResolvedValue(
      makeResponse({
        groupBy: "none",
        series: [point("2026-10-05", "All", "0.65", 12, 5000, 700)],
        groups: [{ group: "All", costUsd: "0.65", inputTokens: 5000, outputTokens: 700, calls: 12, estimatedCalls: 0 }],
      }),
    );
    renderPage();
    await screen.findByTestId("costs-chart");

    expect(lastChart!.data.datasets).toHaveLength(1);
    expect(lastChart!.options.scales.x.stacked).toBe(false);
    expect(lastChart!.options.plugins.legend.display).toBe(false);
    expect(lastChart!.data.datasets[0].borderRadius).toBe(4); // the app's usual rounded bar
    expect(screen.queryByTestId("costs-group-table")).not.toBeInTheDocument();
  });

  it("labels the chart's money axis and tooltips in dollars and totals a stacked day", async () => {
    renderPage();
    await screen.findByTestId("costs-chart");

    const { y } = lastChart!.options.scales;
    const { tooltip } = lastChart!.options.plugins;
    expect(y.ticks.callback(0.25)).toBe("$0.2500");
    expect(y.ticks.callback("2")).toBe("$2.00");
    expect(tooltip.callbacks.title([{ dataIndex: 2 }])).toBe("Wed 7 Oct 2026");
    expect(tooltip.callbacks.label({ dataset: { label: "Ask AI" }, parsed: { y: 0.1 } })).toBe("Ask AI: $0.1000");
    expect(tooltip.callbacks.footer([{ parsed: { y: 0.4 } }, { parsed: { y: 0.1 } }])).toBe("Total: $0.5000");
    expect(tooltip.callbacks.footer([{ parsed: { y: 0.4 } }])).toBe("");
  });

  it("ranks the groups in a second table with each one's share of the total", async () => {
    renderPage();
    await screen.findByTestId("costs-group-table");

    expect(rowsOf("costs-group-table")).toEqual([
      ["Categorization", "$0.5500", "84.6%", "10", "4,000", "500"],
      ["Ask AI", "$0.1000", "15.4%", "2", "1,000", "200"],
    ]);
  });

  it("says estimated embedding tokens are estimates, and only when there are any", async () => {
    vi.mocked(costsApi.getCosts).mockResolvedValue(
      makeResponse({ totals: { costUsd: "0.65", inputTokens: 5000, outputTokens: 700, calls: 12, estimatedCalls: 4 } }),
    );
    renderPage();

    expect(await screen.findByTestId("costs-estimate-note")).toHaveTextContent(/4 of these 12 calls.*estimate/);
  });

  it("has no estimate note when every token count is exact", async () => {
    renderPage();
    await screen.findByTestId("costs-total");

    expect(screen.queryByTestId("costs-estimate-note")).not.toBeInTheDocument();
  });

  it("explains an empty range instead of showing zeros, and draws no chart or table", async () => {
    vi.mocked(costsApi.getCosts).mockResolvedValue(makeResponse({ totals: NONE, series: [], groups: [] }));
    renderPage();

    expect(await screen.findByTestId("costs-empty")).toHaveTextContent(/No model calls were recorded.*not included/);
    expect(screen.queryByTestId("costs-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("costs-period-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("costs-total")).not.toBeInTheDocument();
  });

  it("says so when the costs cannot be loaded", async () => {
    vi.mocked(costsApi.getCosts).mockRejectedValue(new Error("down"));
    renderPage();

    expect(await screen.findByTestId("costs-error")).toHaveTextContent(/could not be loaded/);
  });
});

describe("CostsPage tables sort on every column", () => {
  it("re-sorts the period table by each header, flipping on a second click", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("costs-period-table");
    const firstColumn = () => rowsOf("costs-period-table").map((r) => r[0]);

    await user.click(screen.getByTestId("costs-period-sort-period")); // active on period/desc: now asc
    expect(firstColumn()).toEqual(["Mon 5 Oct 2026", "Wed 7 Oct 2026"]);

    await user.click(screen.getByTestId("costs-period-sort-costUsd")); // ascending cost
    expect(firstColumn()).toEqual(["Wed 7 Oct 2026", "Mon 5 Oct 2026"]);
    await user.click(screen.getByTestId("costs-period-sort-costUsd")); // descending
    expect(firstColumn()).toEqual(["Mon 5 Oct 2026", "Wed 7 Oct 2026"]);

    await user.click(screen.getByTestId("costs-period-sort-calls")); // 2 then 10
    expect(firstColumn()).toEqual(["Wed 7 Oct 2026", "Mon 5 Oct 2026"]);
    await user.click(screen.getByTestId("costs-period-sort-inputTokens")); // 1,000 then 4,000
    expect(firstColumn()).toEqual(["Wed 7 Oct 2026", "Mon 5 Oct 2026"]);
    await user.click(screen.getByTestId("costs-period-sort-outputTokens")); // 100 then 600
    expect(firstColumn()).toEqual(["Wed 7 Oct 2026", "Mon 5 Oct 2026"]);
    expect(screen.getByTestId("costs-period-sort-outputTokens")).toHaveAttribute("aria-sort", "ascending");
  });

  it("re-sorts the group table by each header", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("costs-group-table");
    const firstColumn = () => rowsOf("costs-group-table").map((r) => r[0]);

    expect(firstColumn()).toEqual(["Categorization", "Ask AI"]); // default: most expensive first

    await user.click(screen.getByTestId("costs-group-sort-group"));
    expect(firstColumn()).toEqual(["Ask AI", "Categorization"]);
    await user.click(screen.getByTestId("costs-group-sort-group"));
    expect(firstColumn()).toEqual(["Categorization", "Ask AI"]);

    for (const key of ["costUsd", "share", "calls", "inputTokens", "outputTokens"]) {
      await user.click(screen.getByTestId(`costs-group-sort-${key}`));
      expect(firstColumn()).toEqual(["Ask AI", "Categorization"]); // ascending: the smaller group first
      await user.click(screen.getByTestId(`costs-group-sort-${key}`));
      expect(firstColumn()).toEqual(["Categorization", "Ask AI"]);
    }
  });
});
