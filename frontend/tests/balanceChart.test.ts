import fc from "fast-check";
import { describe, expect, it } from "vitest";

import type { SeriesResponse } from "../src/api/types";
import {
  buildBalanceLines,
  chartLabels,
  COMBINED_COLOR,
  formatAxisTick,
  markerRadius,
  rankSeriesAccounts,
  summarizeSeries,
  toChartNumbers,
} from "../src/lib/balanceChart";
import { CATEGORICAL_PALETTE, OTHER_COLOR } from "../src/lib/chartColors";
import { seriesDayFixture, seriesMonthFixture } from "./balancesFixtures";
import { seriesArb } from "./balanceArbitraries";

// Epic 13 chart data: ranking, folding, labels and the summary sentence. The folding properties are the point: no
// account may be lost or counted twice, a gap may never become a zero, and the folded line is an exact sum.

/** A series with `count` accounts whose last SGD values are given (index 0 first), one point unless more are given. */
function makeSeries(lastValues: (string | null)[], names?: string[]): SeriesResponse {
  const ids = lastValues.map((_, i) => `id-${String(i).padStart(2, "0")}`);
  return {
    start: "2026-07-01",
    end: "2026-07-01",
    granularity: "day",
    accounts: ids.map((id, i) => ({ accountId: id, name: names?.[i] ?? `Account ${i}`, currency: "SGD" })),
    missingAccounts: [],
    points: [
      {
        date: "2026-07-01",
        combinedSgd: "1.00",
        perAccount: Object.fromEntries(ids.map((id, i) => [id, lastValues[i]])),
        approximateAccountIds: [],
      },
    ],
  };
}

describe("rankSeriesAccounts", () => {
  it("puts the largest absolute last balance first, so an overdrawn account is not hidden", () => {
    const series = makeSeries(["1000.00", "-5000.00", "20.00"]);
    expect(rankSeriesAccounts(series)).toEqual(["id-01", "id-00", "id-02"]);
  });

  it("uses an account's last known value when its final point is a gap", () => {
    const series = makeSeries(["10.00", "500.00"]);
    series.points.push({ date: "2026-07-02", combinedSgd: null, perAccount: { "id-00": "9000.00", "id-01": null }, approximateAccountIds: [] });
    // id-00 ends at 9000.00; id-01's last known value is the earlier 500.00
    expect(rankSeriesAccounts(series)).toEqual(["id-00", "id-01"]);
  });

  it("ranks an account that never has a value last", () => {
    expect(rankSeriesAccounts(makeSeries([null, "1.00", "0.00"]))).toEqual(["id-01", "id-02", "id-00"]);
  });

  it("breaks a tie by name without regard to case, then by id", () => {
    const series = makeSeries(["5.00", "5.00", "5.00", "5.00"], ["beta", "Alpha", "alpha", "Beta"]);
    // alpha/Alpha first (equal once case is ignored, so by id), then the two betas the same way
    expect(rankSeriesAccounts(series)).toEqual(["id-01", "id-02", "id-00", "id-03"]);
  });

  it("is a total order that does not depend on the order the accounts arrive in (PBT)", () => {
    fc.assert(
      fc.property(seriesArb, fc.nat(), (series, seed) => {
        const reversed = { ...series, accounts: [...series.accounts].reverse() };
        const rotated = { ...series, accounts: [...series.accounts.slice(seed % (series.accounts.length || 1)), ...series.accounts.slice(0, seed % (series.accounts.length || 1))] };
        const ranking = rankSeriesAccounts(series);
        expect(rankSeriesAccounts(reversed)).toEqual(ranking);
        expect(rankSeriesAccounts(rotated)).toEqual(ranking);
        expect(new Set(ranking).size).toBe(series.accounts.length);
      }),
    );
  });

  it("agrees with an independent sort (PBT)", () => {
    const cents = (v: string) => BigInt(v.replace(".", ""));
    fc.assert(
      fc.property(seriesArb, (series) => {
        const lastSize = (id: string): bigint => {
          for (let i = series.points.length - 1; i >= 0; i -= 1) {
            const v = series.points[i].perAccount[id];
            if (v !== null) return cents(v) < 0n ? -cents(v) : cents(v);
          }
          return -1n;
        };
        const expected = [...series.accounts]
          .sort((a, b) => {
            const sa = lastSize(a.accountId);
            const sb = lastSize(b.accountId);
            if (sa !== sb) return sa > sb ? -1 : 1;
            const na = a.name.toLowerCase();
            const nb = b.name.toLowerCase();
            if (na !== nb) return na < nb ? -1 : 1;
            return a.accountId < b.accountId ? -1 : 1;
          })
          .map((a) => a.accountId);
        expect(rankSeriesAccounts(series)).toEqual(expected);
      }),
    );
  });
});

describe("buildBalanceLines", () => {
  it("draws the combined total first, then the accounts by rank in the palette's order, from the real series", () => {
    const lines = buildBalanceLines(seriesDayFixture(), "light");
    expect(lines.map((l) => l.label)).toEqual(["Combined total", "Main", "Trust USD", "Offshore EUR"]);
    expect(lines.map((l) => l.kind)).toEqual(["combined", "account", "account", "account"]);
    expect(lines[0].color).toBe(COMBINED_COLOR.light);
    expect(lines.slice(1).map((l) => l.color)).toEqual([CATEGORICAL_PALETTE[0], CATEGORICAL_PALETTE[1], CATEGORICAL_PALETTE[2]]);
    expect(lines[0].width).toBeGreaterThan(lines[1].width);
  });

  it("keeps a gap a gap: the account with no exchange rate is null at every point, never zero", () => {
    const lines = buildBalanceLines(seriesDayFixture(), "light");
    expect(lines[3].values).toEqual([null, null, null, null, null]);
    expect(lines[1].values).toEqual(["1100.00", "1100.00", "1100.00", "1100.00", "1100.00"]);
  });

  it("uses the theme's ink colour for the combined line", () => {
    expect(buildBalanceLines(seriesDayFixture(), "dark")[0].color).toBe(COMBINED_COLOR.dark);
    expect(COMBINED_COLOR.light).not.toBe(COMBINED_COLOR.dark);
  });

  it.each([
    [0, 1, 0],
    [1, 2, 0],
    [7, 8, 0],
    [8, 9, 1],
    [14, 9, 7],
  ])("with %i accounts draws %i lines and folds %i", (accounts, lineCount, folded) => {
    const series = makeSeries(Array.from({ length: accounts }, (_, i) => `${1000 - i * 10}.00`));
    const lines = buildBalanceLines(series, "light");
    expect(lines).toHaveLength(lineCount);
    const other = lines.find((l) => l.kind === "other");
    expect(other?.accountIds.length ?? 0).toBe(folded);
    if (other) expect(other.label).toBe(`Other accounts (${folded})`);
  });

  it("folds the SMALLEST accounts, in grey, summing them exactly", () => {
    const series = makeSeries(["100.10", "90.00", "80.00", "70.00", "60.00", "50.00", "40.00", "30.05", "20.00", "-5.50"]);
    const lines = buildBalanceLines(series, "light");
    expect(lines.slice(1, 8).map((l) => l.label)).toEqual(["Account 0", "Account 1", "Account 2", "Account 3", "Account 4", "Account 5", "Account 6"]);
    const other = lines[8];
    expect(other.color).toBe(OTHER_COLOR);
    expect(other.values).toEqual(["44.55"]); // 30.05 + 20.00 + -5.50, exactly
  });

  it("sums only the known members of the folded line and leaves a gap only when every member has one", () => {
    const series = makeSeries(["9.00", "8.00", "7.00", "6.00", "5.00", "4.00", "3.00", "2.00", "1.00"]);
    const original = series.points[0].perAccount;
    // The seven largest keep their values on later days, so the two smallest (id-07, id-08) stay the folded pair.
    series.points.push({ date: "2026-07-02", combinedSgd: null, perAccount: { ...original, "id-07": null }, approximateAccountIds: [] });
    series.points.push({ date: "2026-07-03", combinedSgd: null, perAccount: { ...original, "id-07": null, "id-08": null }, approximateAccountIds: [] });
    const other = buildBalanceLines(series, "light")[8];
    expect(other.accountIds).toEqual(["id-07", "id-08"]);
    expect(other.values).toEqual(["3.00", "1.00", null]); // both known; only id-08 known; neither known
  });

  it("accounts for every plotted account exactly once, and never turns a gap into a number (PBT)", () => {
    fc.assert(
      fc.property(seriesArb, (series) => {
        const lines = buildBalanceLines(series, "light");
        const placed = lines.flatMap((l) => l.accountIds);
        expect([...placed].sort()).toEqual(series.accounts.map((a) => a.accountId).sort());
        expect(new Set(placed).size).toBe(placed.length);
        const n = series.accounts.length;
        expect(lines).toHaveLength(1 + Math.min(7, n) + (n > 7 ? 1 : 0));
        for (const line of lines.filter((l) => l.kind === "account")) {
          expect(line.values).toEqual(series.points.map((p) => p.perAccount[line.accountIds[0]]));
        }
        expect(lines[0].values).toEqual(series.points.map((p) => p.combinedSgd));
      }),
    );
  });

  it("makes the folded line the exact sum of its members' known values (PBT)", () => {
    const cents = (v: string) => BigInt(v.replace(".", ""));
    fc.assert(
      fc.property(seriesArb, (series) => {
        const other = buildBalanceLines(series, "light").find((l) => l.kind === "other");
        if (!other) return;
        series.points.forEach((point, p) => {
          const known = other.accountIds.map((id) => point.perAccount[id]).filter((v): v is string => v !== null);
          if (known.length === 0) {
            expect(other.values[p]).toBeNull();
          } else {
            const total = known.reduce((sum, v) => sum + cents(v), 0n);
            expect(cents(other.values[p] as string)).toBe(total);
          }
        });
      }),
    );
  });

  it("uses at most eight colours for accounts, all different, none the combined line's (PBT)", () => {
    fc.assert(
      fc.property(seriesArb, (series) => {
        const lines = buildBalanceLines(series, "light");
        const colours = lines.slice(1).map((l) => l.color);
        expect(new Set(colours).size).toBe(colours.length);
        expect(colours.length).toBeLessThanOrEqual(8);
        expect(colours).not.toContain(lines[0].color);
      }),
    );
  });
});

describe("chartLabels", () => {
  it("labels a daily range inside one year with the day and month", () => {
    expect(chartLabels(seriesDayFixture())).toEqual(["29 Jul", "30 Jul", "31 Jul", "1 Aug", "2 Aug"]);
  });

  it("adds the year to every daily label when the range crosses a year", () => {
    const series = { granularity: "day" as const, points: ["2025-12-30", "2025-12-31", "2026-01-01"].map((date) => ({ date })) };
    expect(chartLabels(series as unknown as SeriesResponse)).toEqual(["30 Dec 2025", "31 Dec 2025", "1 Jan 2026"]);
  });

  it("labels month ends as month and year, and a range end that is not a month end as its day", () => {
    expect(chartLabels(seriesMonthFixture())).toEqual(["May 2026", "Jun 2026", "Jul 2026", "Aug 2026", "Sep 2026", "18 Oct 2026"]);
  });

  it("knows February's last day in a leap year and in an ordinary one", () => {
    const series = { granularity: "month" as const, points: ["2028-02-29", "2027-02-28", "2027-02-27"].map((date) => ({ date })) };
    expect(chartLabels(series as unknown as SeriesResponse)).toEqual(["Feb 2028", "Feb 2027", "27 Feb 2027"]);
  });

  it("gives one label per point, and none for none", () => {
    expect(chartLabels({ granularity: "day", points: [] })).toEqual([]);
    fc.assert(fc.property(seriesArb, (series) => chartLabels(series).length === series.points.length));
  });
});

describe("summarizeSeries", () => {
  it("states the first, the last and the exact change", () => {
    expect(summarizeSeries(seriesMonthFixture())).toBe(
      "Combined balance went from SGD 1,075.00 on 31 May 2026 to SGD 1,880.00 on 18 Oct 2026 (+SGD 805.00).",
    );
  });

  it("states a fall with a minus sign", () => {
    const series = { points: [{ date: "2026-07-01", combinedSgd: "1000.00" }, { date: "2026-07-02", combinedSgd: "-1500.50" }] };
    expect(summarizeSeries(series as unknown as SeriesResponse)).toBe(
      "Combined balance went from SGD 1,000.00 on 1 Jul 2026 to SGD -1,500.50 on 2 Jul 2026 (-SGD 2,500.50).",
    );
  });

  it("says no change when there is none", () => {
    const series = { points: [{ date: "2026-07-01", combinedSgd: "5.00" }, { date: "2026-07-02", combinedSgd: "5.00" }] };
    expect(summarizeSeries(series as unknown as SeriesResponse)).toContain("(no change)");
  });

  it("skips leading and trailing points with no combined total", () => {
    const series = {
      points: [
        { date: "2026-07-01", combinedSgd: null },
        { date: "2026-07-02", combinedSgd: "10.00" },
        { date: "2026-07-03", combinedSgd: "12.50" },
        { date: "2026-07-04", combinedSgd: null },
      ],
    };
    expect(summarizeSeries(series as unknown as SeriesResponse)).toBe(
      "Combined balance went from SGD 10.00 on 2 Jul 2026 to SGD 12.50 on 3 Jul 2026 (+SGD 2.50).",
    );
  });

  it("describes a single known point, and an empty range", () => {
    expect(summarizeSeries({ points: [{ date: "2026-07-01", combinedSgd: "7.00" }] } as unknown as SeriesResponse)).toBe(
      "The combined balance on 1 Jul 2026 is SGD 7.00.",
    );
    expect(summarizeSeries({ points: [{ date: "2026-07-01", combinedSgd: null }] } as unknown as SeriesResponse)).toBe(
      "There is no combined balance in this range.",
    );
    expect(summarizeSeries({ points: [] })).toBe("There is no combined balance in this range.");
  });
});

describe("toChartNumbers and markerRadius", () => {
  it("turns amounts into numbers for plotting and keeps gaps as null", () => {
    expect(toChartNumbers(["1030.00", null, "-5.50"])).toEqual([1030, null, -5.5]);
  });

  it("draws markers only on short lines", () => {
    expect(markerRadius(40)).toBe(3);
    expect(markerRadius(41)).toBe(0);
    expect(markerRadius(1)).toBe(3);
  });
});

describe("formatAxisTick", () => {
  it("groups thousands and keeps at most two decimals", () => {
    expect(formatAxisTick(0)).toBe("0");
    expect(formatAxisTick(1100)).toBe("1,100");
    expect(formatAxisTick("12345.678")).toBe("12,345.68");
    expect(formatAxisTick(-1250.5)).toBe("-1,250.5");
    expect(formatAxisTick(1000000)).toBe("1,000,000");
  });
});
