import { describe, expect, it } from "vitest";

import { CATEGORICAL_PALETTE, OTHER_LABEL, buildCategoricalSeries } from "../src/lib/chartColors";

interface Point {
  month: string;
  key: string;
  value: number;
}

function point(month: string, key: string, value: number): Point {
  return { month, key, value };
}

describe("buildCategoricalSeries", () => {
  it("assigns distinct palette colors per series when within the palette size", () => {
    const points = [point("2026-01", "Groceries", 100), point("2026-01", "Dining", 50)];
    const series = buildCategoricalSeries(points, ["2026-01"], (p) => p.month, (p) => p.key, (p) => p.value);

    expect(series.map((s) => s.label)).toEqual(["Groceries", "Dining"]);
    expect(series.map((s) => s.color)).toEqual([CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[1]]);
    // no two series ever share a color
    expect(new Set(series.map((s) => s.color)).size).toBe(series.length);
  });

  it("sums matching points per month into each series", () => {
    const points = [
      point("2026-01", "Groceries", 100),
      point("2026-01", "Groceries", 25),
      point("2026-02", "Groceries", 40),
    ];
    const series = buildCategoricalSeries(points, ["2026-01", "2026-02"], (p) => p.month, (p) => p.key, (p) => p.value);

    expect(series[0].data).toEqual([125, 40]);
  });

  it("fills a zero for a month with no matching points", () => {
    const points = [point("2026-01", "Groceries", 100)];
    const series = buildCategoricalSeries(points, ["2026-01", "2026-02"], (p) => p.month, (p) => p.key, (p) => p.value);

    expect(series[0].data).toEqual([100, 0]);
  });

  it("folds overflow beyond the palette size into a single 'Other' series, never generating a 9th color", () => {
    // 9 distinct keys -- one more than the 8-slot palette
    const points = Array.from({ length: 9 }, (_, i) => point("2026-01", `Cat${i}`, (9 - i) * 10));
    const series = buildCategoricalSeries(points, ["2026-01"], (p) => p.month, (p) => p.key, (p) => p.value);

    // 7 named (top by total) + 1 "Other" bucket for the rest
    expect(series).toHaveLength(8);
    expect(series[7].label).toBe(OTHER_LABEL);
    expect(series.slice(0, 7).map((s) => s.color)).toEqual(CATEGORICAL_PALETTE.slice(0, 7));

    // the two smallest-total keys (Cat7=20, Cat8=10) get folded into Other
    expect(series[7].data[0]).toBe(20 + 10);
    // and nothing in the named series duplicates a folded key
    expect(series.slice(0, 7).map((s) => s.label)).not.toContain("Cat7");
    expect(series.slice(0, 7).map((s) => s.label)).not.toContain("Cat8");
  });

  it("ranks named series by total value, largest first", () => {
    const points = [point("2026-01", "Small", 5), point("2026-01", "Big", 500), point("2026-01", "Medium", 50)];
    const series = buildCategoricalSeries(points, ["2026-01"], (p) => p.month, (p) => p.key, (p) => p.value);

    expect(series.map((s) => s.label)).toEqual(["Big", "Medium", "Small"]);
  });
});
