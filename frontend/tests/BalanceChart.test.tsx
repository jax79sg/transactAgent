import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as balancesApi from "../src/api/balances";
import { ApiError } from "../src/api/client";
import type { SeriesResponse } from "../src/api/types";
import { BalanceChart } from "../src/components/balances/BalanceChart";
import { ThemeProvider } from "../src/context/ThemeContext";
import { COMBINED_COLOR } from "../src/lib/balanceChart";
import { CATEGORICAL_PALETTE, OTHER_COLOR } from "../src/lib/chartColors";
import { renderWithQueryClient } from "./balanceTestUtils";
import { seriesDayFixture, seriesMonthFixture } from "./balancesFixtures";

// The chart is drawn on a canvas jsdom does not have; what matters is what the component hands it.
interface Captured {
  data: { labels: string[]; datasets: Record<string, unknown>[] };
  options: {
    scales: { x: { ticks: { color: string; maxTicksLimit: number } }; y: { ticks: { color: string; callback: (v: number) => string } } };
    plugins: { tooltip: { callbacks: { title: (items: { dataIndex: number }[]) => string; label: (item: { datasetIndex: number; dataIndex: number; dataset: { label: string } }) => string } } };
  };
}
let chart: Captured | null = null;
vi.mock("react-chartjs-2", () => ({
  Line: (props: unknown) => {
    chart = props as Captured;
    return <canvas data-testid="line-canvas" />;
  },
}));
vi.mock("../src/api/balances");

const getSeries = () => vi.mocked(balancesApi.getBalanceSeries);

function setup(today: string | null = "2026-10-18") {
  return renderWithQueryClient(
    <ThemeProvider>
      <BalanceChart today={today} />
    </ThemeProvider>,
  );
}

function manyAccounts(count: number): SeriesResponse {
  const accounts = Array.from({ length: count }, (_, i) => ({ accountId: `id-${String(i).padStart(2, "0")}`, name: `Account ${i}`, currency: "SGD" }));
  return {
    start: "2026-07-01",
    end: "2026-07-02",
    granularity: "day",
    accounts,
    missingAccounts: [],
    points: ["2026-07-01", "2026-07-02"].map((date) => ({
      date,
      combinedSgd: "100.00",
      perAccount: Object.fromEntries(accounts.map((a, i) => [a.accountId, `${1000 - i * 10}.00`])),
      approximateAccountIds: [],
    })),
  };
}

afterEach(() => {
  chart = null;
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("BalanceChart: what it asks for", () => {
  it("sends no dates at first, so the API supplies the last 12 months, and prefills the inputs from the answer", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    expect(getSeries()).toHaveBeenCalledWith({ granularity: "auto" });
    expect(screen.getByTestId("series-from")).toHaveValue("2026-07-29");
    expect(screen.getByTestId("series-to")).toHaveValue("2026-08-02");
    expect(screen.getByTestId("series-from")).toHaveAttribute("max", "2026-10-18");
    expect(screen.getByTestId("series-granularity-auto")).toBeChecked();
  });

  it("sends BOTH dates once the owner edits one", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");

    fireEvent.change(screen.getByTestId("series-from"), { target: { value: "2026-07-30" } });
    await waitFor(() => expect(getSeries()).toHaveBeenLastCalledWith({ from: "2026-07-30", to: "2026-08-02", granularity: "auto" }));

    fireEvent.change(screen.getByTestId("series-to"), { target: { value: "2026-08-01" } });
    await waitFor(() => expect(getSeries()).toHaveBeenLastCalledWith({ from: "2026-07-30", to: "2026-08-01", granularity: "auto" }));
  });

  it("ignores an empty, ancient or future date instead of asking about it", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    for (const value of ["", "1999-12-31", "2026-12-01"]) fireEvent.change(screen.getByTestId("series-from"), { target: { value } });
    expect(getSeries()).toHaveBeenCalledTimes(1);
  });

  it("sends the point choice it was given, and says which the API resolved to", async () => {
    getSeries().mockImplementation(async (params) => (params?.granularity === "month" ? seriesMonthFixture() : seriesDayFixture()));
    setup();
    await screen.findByTestId("series-chart");
    expect(screen.getByTestId("series-resolved")).toHaveTextContent("Showing every day");

    await userEvent.setup().click(screen.getByTestId("series-granularity-month"));

    await waitFor(() => expect(getSeries()).toHaveBeenLastCalledWith({ granularity: "month" }));
    await waitFor(() => expect(screen.getByTestId("series-resolved")).toHaveTextContent("Showing month-end points"));
    expect(screen.getByTestId("series-granularity-month")).toBeChecked();
  });

  it("goes back to the last 12 months, dropping the dates but keeping the point choice", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    const user = userEvent.setup();
    await user.click(screen.getByTestId("series-granularity-day"));
    fireEvent.change(screen.getByTestId("series-from"), { target: { value: "2026-07-30" } });
    await waitFor(() => expect(getSeries()).toHaveBeenLastCalledWith({ from: "2026-07-30", to: "2026-08-02", granularity: "day" }));

    await user.click(screen.getByTestId("series-reset"));

    await waitFor(() => expect(getSeries()).toHaveBeenLastCalledWith({ granularity: "day" }));
  });
});

describe("BalanceChart: what it draws", () => {
  it("hands the chart the combined line first, then the accounts by rank, with exact values and gaps kept", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");

    const datasets = chart!.data.datasets;
    expect(datasets.map((d) => d.label)).toEqual(["Combined total", "Main", "Trust USD", "Offshore EUR"]);
    expect(datasets[0].data).toEqual([1880, 1880, 1880, 1880, 1880]);
    expect(datasets[3].data).toEqual([null, null, null, null, null]); // no exchange rate: a gap, never zero
    expect(datasets.map((d) => d.borderColor)).toEqual([COMBINED_COLOR.light, CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[1], CATEGORICAL_PALETTE[2]]);
    expect(datasets.every((d) => d.spanGaps === false && d.tension === 0)).toBe(true);
    expect(datasets[0].borderWidth).toBeGreaterThan(datasets[1].borderWidth as number);
    expect(chart!.data.labels).toEqual(["29 Jul", "30 Jul", "31 Jul", "1 Aug", "2 Aug"]);
  });

  it("folds the smallest accounts into one grey line when there are more than seven", async () => {
    getSeries().mockResolvedValue(manyAccounts(14));
    setup();
    await screen.findByTestId("series-chart");
    const datasets = chart!.data.datasets;
    expect(datasets).toHaveLength(9);
    expect(datasets[8].label).toBe("Other accounts (7)");
    expect(datasets[8].borderColor).toBe(OTHER_COLOR);
  });

  it("draws markers only on a short line", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    const { unmount } = setup();
    await screen.findByTestId("series-chart");
    expect(chart!.data.datasets[0].pointRadius).toBe(3);
    unmount();

    const long = manyAccounts(1);
    long.points = Array.from({ length: 50 }, (_, i) => ({ ...long.points[0], date: `2026-08-${String((i % 28) + 1).padStart(2, "0")}` }));
    getSeries().mockResolvedValue(long);
    setup();
    await waitFor(() => expect(chart!.data.datasets[0].pointRadius).toBe(0));
  });

  it("formats the axis, and the tooltip title and rows, from the exact figures", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    const { options } = chart!;
    expect(options.scales.y.ticks.callback(1100)).toBe("1,100");
    expect(options.plugins.tooltip.callbacks.title([{ dataIndex: 2 }])).toBe("31 Jul 2026");
    expect(options.plugins.tooltip.callbacks.label({ datasetIndex: 1, dataIndex: 2, dataset: { label: "Main" } })).toBe("Main: SGD 1,100.00");
    expect(options.plugins.tooltip.callbacks.label({ datasetIndex: 0, dataIndex: 0, dataset: { label: "Combined total" } })).toBe("Combined total: SGD 1,880.00");
  });

  it("takes its chrome and the combined line's ink from the dark theme", async () => {
    localStorage.setItem("transactagent_theme", "dark");
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    expect(chart!.data.datasets[0].borderColor).toBe(COMBINED_COLOR.dark);
    expect(chart!.options.scales.x.ticks.color).toBe("#cbd5e1");
  });
});

describe("BalanceChart: what is written around it", () => {
  it("writes the exact start, end and change, and uses the same sentence as the chart's label", async () => {
    getSeries().mockResolvedValue(seriesMonthFixture());
    setup();
    const element = await screen.findByTestId("series-summary");
    expect(element).toHaveTextContent("Combined balance went from SGD 1,075.00 on 31 May 2026 to SGD 1,880.00 on 18 Oct 2026 (+SGD 805.00).");
    expect(screen.getByTestId("series-chart")).toHaveAttribute("aria-label", element.textContent ?? "");
    expect(screen.getByTestId("series-chart")).toHaveAttribute("role", "img");
  });

  it("names the accounts that cannot be plotted and why, and explains a gap", async () => {
    getSeries().mockResolvedValue(seriesDayFixture());
    setup();
    expect(await screen.findByTestId("series-not-plotted")).toHaveTextContent("Not plotted: Fresh (anchor required)");
    expect(screen.getByTestId("series-gap-note")).toHaveTextContent("A break in a line means no exchange rate was available for that date.");
  });

  it("leaves the gap note out when there is no gap", async () => {
    const series = manyAccounts(2);
    getSeries().mockResolvedValue(series);
    setup();
    await screen.findByTestId("series-chart");
    expect(screen.queryByTestId("series-gap-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("series-not-plotted")).not.toBeInTheDocument();
  });

  it("says what to do when no account can be plotted, and still names the missing ones", async () => {
    const series = seriesDayFixture();
    series.accounts = [];
    series.points = series.points.map((p) => ({ ...p, combinedSgd: null, perAccount: {} }));
    getSeries().mockResolvedValue(series);
    setup();
    expect(await screen.findByTestId("series-empty")).toHaveTextContent("Enter a balance for at least one account to see the chart.");
    expect(screen.queryByTestId("series-chart")).not.toBeInTheDocument();
    expect(screen.getByTestId("series-not-plotted")).toBeInTheDocument();
  });

  it("shows a loading line first", () => {
    getSeries().mockReturnValue(new Promise(() => {}));
    setup();
    expect(screen.getByTestId("series-loading")).toBeInTheDocument();
  });
});

describe("BalanceChart: when the API refuses", () => {
  it("shows the sentence beneath the controls and keeps the last good chart", async () => {
    getSeries().mockResolvedValueOnce(seriesDayFixture());
    setup();
    await screen.findByTestId("series-chart");
    getSeries().mockRejectedValue(new ApiError(400, { error: "invalid_date_range", message: "x" }));

    fireEvent.change(screen.getByTestId("series-from"), { target: { value: "2026-09-01" } }); // after the end

    expect(await screen.findByTestId("series-error")).toHaveTextContent("The start must be on or before the end");
    expect(screen.getByTestId("series-chart")).toBeInTheDocument();
    expect(screen.getByTestId("series-summary")).toBeInTheDocument();
  });

  it("offers Try again for a server fault, and does not retry on its own", async () => {
    getSeries().mockRejectedValueOnce(new ApiError(500, { error: "unknown", message: "Internal Server Error" }));
    setup();
    expect(await screen.findByTestId("series-error")).toHaveTextContent("The server had a problem. Please try again.");
    expect(getSeries()).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("series-loading")).not.toBeInTheDocument();

    getSeries().mockResolvedValue(seriesDayFixture());
    await userEvent.setup().click(screen.getByTestId("series-retry"));
    expect(await screen.findByTestId("series-chart")).toBeInTheDocument();
  });

  it("names the range limit in words", async () => {
    getSeries().mockRejectedValue(new ApiError(400, { error: "range_too_large", message: "x" }));
    setup();
    expect(await screen.findByTestId("series-error")).toHaveTextContent("That range has too many points. Choose a shorter range or month-end points.");
  });
});
