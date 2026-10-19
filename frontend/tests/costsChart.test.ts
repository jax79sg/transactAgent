import { describe, expect, it } from "vitest";

import type { CostGranularity, CostPoint, CostsResponse } from "../src/api/types";
import { CATEGORICAL_PALETTE, OTHER_COLOR, OTHER_LABEL } from "../src/lib/chartColors";
import {
  axisLabel,
  buildCostDatasets,
  buildPeriodRows,
  groupLabel,
  periodLabel,
  sortRows,
} from "../src/lib/costsChart";

function point(period: string, group: string, costUsd: string, calls = 1, inputTokens = 100, outputTokens = 10): CostPoint {
  return { period, group, costUsd, calls, inputTokens, outputTokens, estimatedCalls: 0 };
}

function response(overrides: Partial<CostsResponse> & { series: CostPoint[]; groups: CostsResponse["groups"] }): CostsResponse {
  return {
    currency: "USD",
    dateFrom: "2026-10-01",
    dateTo: "2026-10-03",
    granularity: "day",
    groupBy: "purpose",
    timezone: "UTC",
    periods: ["2026-10-01", "2026-10-02", "2026-10-03"],
    totals: { costUsd: "0", inputTokens: 0, outputTokens: 0, calls: 0, estimatedCalls: 0 },
    ...overrides,
  };
}

function group(name: string, costUsd: string) {
  return { group: name, costUsd, inputTokens: 0, outputTokens: 0, calls: 1, estimatedCalls: 0 };
}

describe("axisLabel and periodLabel", () => {
  it.each<[CostGranularity, string, string]>([
    ["day", "2026-10-05", "5 Oct"],
    ["week", "2026-10-05", "Wk 5 Oct"],
    ["month", "2026-10-01", "Oct 2026"],
  ])("a %s axis label for %s reads %s", (granularity, period, label) => {
    expect(axisLabel(period, granularity)).toBe(label);
  });

  it.each<[CostGranularity, string, string]>([
    ["day", "2026-10-05", "Mon 5 Oct 2026"],
    ["week", "2026-10-05", "Week of 5 Oct 2026"],
    ["month", "2026-10-01", "October 2026"],
  ])("a %s table label for %s reads %s", (granularity, period, label) => {
    expect(periodLabel(period, granularity)).toBe(label);
  });

  it("never shifts a day with the machine's own time zone (the first and last day of a month, a year end)", () => {
    expect(axisLabel("2026-10-01", "day")).toBe("1 Oct");
    expect(axisLabel("2026-10-31", "day")).toBe("31 Oct");
    expect(axisLabel("2026-12-31", "day")).toBe("31 Dec");
    expect(axisLabel("2027-01-01", "day")).toBe("1 Jan");
  });
});

describe("groupLabel", () => {
  it("names the four purposes and leaves a model name or an unknown purpose as it is", () => {
    expect(groupLabel("statement_extraction", "purpose")).toBe("Statement extraction");
    expect(groupLabel("embedding", "purpose")).toBe("Embeddings");
    expect(groupLabel("something_new", "purpose")).toBe("something_new");
    expect(groupLabel("gemini-3.5-flash-lite", "model")).toBe("gemini-3.5-flash-lite");
    expect(groupLabel("embedding", "model")).toBe("embedding");
  });
});

describe("buildCostDatasets", () => {
  it("has one dataset per group over every period, with zero where there was no spend", () => {
    const datasets = buildCostDatasets(
      response({
        series: [point("2026-10-01", "categorization", "0.5"), point("2026-10-03", "categorization", "0.25")],
        groups: [group("categorization", "0.75")],
      }),
    );

    expect(datasets).toHaveLength(1);
    expect(datasets[0].data).toEqual([0.5, 0, 0.25]);
    expect(datasets[0].label).toBe("Categorization");
  });

  it("gives each purpose its own fixed color, whichever purposes are present or how they rank", () => {
    const all = buildCostDatasets(
      response({
        series: [],
        groups: [group("ask_ai", "9"), group("embedding", "5"), group("categorization", "2"), group("statement_extraction", "1")],
      }),
    );
    const onlyAskAi = buildCostDatasets(response({ series: [], groups: [group("ask_ai", "9")] }));

    const colorOf = (datasets: typeof all, name: string) => datasets.find((d) => d.group === name)!.color;
    expect(colorOf(all, "statement_extraction")).toBe(CATEGORICAL_PALETTE[0]);
    expect(colorOf(all, "categorization")).toBe(CATEGORICAL_PALETTE[1]);
    expect(colorOf(all, "embedding")).toBe(CATEGORICAL_PALETTE[2]);
    expect(colorOf(all, "ask_ai")).toBe(CATEGORICAL_PALETTE[3]);
    expect(colorOf(onlyAskAi, "ask_ai")).toBe(colorOf(all, "ask_ai"));  // filtering must not repaint the survivor
  });

  it("colors models by their cost rank, most expensive first, and never repeats a color", () => {
    const datasets = buildCostDatasets(
      response({ groupBy: "model", series: [], groups: [group("big", "5"), group("small", "1")] }),
    );

    expect(datasets.map((d) => d.color)).toEqual([CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[1]]);
  });

  it("folds models past the palette into one Other series instead of inventing hues", () => {
    const names = Array.from({ length: 10 }, (_, i) => `model-${i}`);
    const series = names.map((name, i) => point("2026-10-01", name, String(10 - i)));
    const datasets = buildCostDatasets(
      response({ groupBy: "model", series, groups: names.map((n, i) => group(n, String(10 - i))) }),
    );

    expect(datasets).toHaveLength(8); // 7 named + Other
    const other = datasets[7];
    expect([other.label, other.color]).toEqual([OTHER_LABEL, OTHER_COLOR]);
    expect(other.data).toEqual([3 + 2 + 1, 0, 0]); // the last three models: 10-7, 10-8, 10-9
    expect(new Set(datasets.map((d) => d.color)).size).toBe(8);
  });

  it("never folds purposes: there are only four and each keeps its hue", () => {
    const datasets = buildCostDatasets(response({ series: [], groups: [group("a", "1"), group("b", "1"), group("c", "1"), group("d", "1"), group("e", "1"), group("f", "1"), group("g", "1"), group("h", "1")] }));

    expect(datasets.some((d) => d.label === OTHER_LABEL)).toBe(false);
  });

  it("is empty when nothing was recorded", () => {
    expect(buildCostDatasets(response({ series: [], groups: [] }))).toEqual([]);
  });
});

describe("buildPeriodRows", () => {
  it("sums the groups of each period and skips periods without calls", () => {
    const rows = buildPeriodRows(
      response({
        series: [
          point("2026-10-01", "a", "1.5", 2, 200, 20),
          point("2026-10-01", "b", "0.5", 1, 100, 10),
          point("2026-10-03", "a", "2", 4, 400, 40),
        ],
        groups: [],
      }),
    );

    expect(rows).toEqual([
      { period: "2026-10-01", costUsd: 2, calls: 3, inputTokens: 300, outputTokens: 30 },
      { period: "2026-10-03", costUsd: 2, calls: 4, inputTokens: 400, outputTokens: 40 },
    ]);
  });
});

describe("sortRows", () => {
  // The two equal-cost rows arrive in the OPPOSITE order to the tie-break (10-03 before 10-02), so only a real
  // tie-break puts them right -- a stable sort that leaves ties alone would not.
  const rows = [
    { period: "2026-10-03", costUsd: 5, group: "c" },
    { period: "2026-10-01", costUsd: 1, group: "a" },
    { period: "2026-10-02", costUsd: 5, group: "b" },
  ];

  it("sorts numbers numerically, ascending and descending", () => {
    expect(sortRows(rows, "costUsd", "asc", "period").map((r) => r.costUsd)).toEqual([1, 5, 5]);
    expect(sortRows(rows, "costUsd", "desc", "period").map((r) => r.costUsd)).toEqual([5, 5, 1]);
  });

  it("sorts text alphabetically", () => {
    expect(sortRows(rows, "group", "asc", "period").map((r) => r.group)).toEqual(["a", "b", "c"]);
    expect(sortRows(rows, "group", "desc", "period").map((r) => r.group)).toEqual(["c", "b", "a"]);
  });

  it("breaks ties by the tiebreak column, always ascending, so equal rows do not shuffle", () => {
    expect(sortRows(rows, "costUsd", "desc", "period").map((r) => r.period)).toEqual(["2026-10-02", "2026-10-03", "2026-10-01"]);
    expect(sortRows(rows, "costUsd", "asc", "period").map((r) => r.period)).toEqual(["2026-10-01", "2026-10-02", "2026-10-03"]);
  });

  it("does not change the list it was given", () => {
    const copy = [...rows];
    sortRows(rows, "costUsd", "asc", "period");
    expect(rows).toEqual(copy);
  });

  it("compares numbers as numbers, not as text (9 before 10)", () => {
    const nums = [{ k: 10, t: "x" }, { k: 9, t: "y" }];
    expect(sortRows(nums, "k", "asc", "t").map((r) => r.k)).toEqual([9, 10]);
  });
});
