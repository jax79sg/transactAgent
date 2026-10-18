// Epic 13 (US-13.5, Question 2 = A): what the balance chart draws, as plain data. The combined total is one thick line
// in the theme's ink colour; the 7 accounts with the largest balance each get a palette colour; any account beyond
// those is folded into a single grey "Other accounts (N)" line (the project's rule of at most eight distinct colours).
// Values stay the API's exact strings; `Number()` happens only when the arrays are handed to Chart.js, so sums made
// here (the folded line) are exact. A null is a gap (no usable exchange rate that day) and is never turned into zero.

import type { SeriesResponse } from "../api/types";
import type { Theme } from "../context/ThemeContext";
import { addDays, monthName } from "./balances";
import { CATEGORICAL_PALETTE, OTHER_COLOR } from "./chartColors";
import { formatDay } from "./duplicates";
import { formatAmount, fromCents, subtractAmounts, toCents } from "./money";

export const MAX_NAMED_ACCOUNTS = 7;
/** Markers (the dots) are drawn only when a line has this many points or fewer; hovering always shows one. */
export const MARKER_LIMIT = 40;

export const COMBINED_COLOR: Record<Theme, string> = { light: "#0f172a", dark: "#f1f5f9" }; // slate-900, slate-100

export type BalanceLineKind = "combined" | "account" | "other";

export interface BalanceLine {
  key: string;
  kind: BalanceLineKind;
  label: string;
  color: string;
  width: number;
  /** The accounts this line stands for: itself, or the folded ones. Empty for the combined total. */
  accountIds: string[];
  /** One exact amount per point, or null for a gap. */
  values: (string | null)[];
}

type SeriesInput = Pick<SeriesResponse, "accounts" | "points">;

function valueAt(point: SeriesResponse["points"][number], accountId: string): string | null {
  return point.perAccount[accountId] ?? null;
}

/** Absolute cents of an account's last non-null value in the range; -1 when it never has one (ranks last). */
function lastAbsoluteCents(series: SeriesInput, accountId: string): bigint {
  for (let i = series.points.length - 1; i >= 0; i -= 1) {
    const value = valueAt(series.points[i], accountId);
    if (value !== null) {
      const cents = toCents(value);
      return cents < 0n ? -cents : cents;
    }
  }
  return -1n;
}

/**
 * The plotted accounts, largest first by the absolute value of their last known SGD balance in the range (an overdrawn
 * account is not hidden), ties by name (case-insensitive) and then id. Independent of the order of `series.accounts`.
 */
export function rankSeriesAccounts(series: SeriesInput): string[] {
  const ranked = series.accounts.map((account) => ({
    id: account.accountId,
    name: account.name.toLowerCase(),
    size: lastAbsoluteCents(series, account.accountId),
  }));
  ranked.sort((a, b) => {
    if (a.size !== b.size) return a.size > b.size ? -1 : 1;
    if (a.name !== b.name) return a.name < b.name ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
  return ranked.map((entry) => entry.id);
}

/** The exact sum of the non-null amounts, or null when every one is null (consistent with the API's combined total). */
function sumKnown(values: (string | null)[]): string | null {
  const known = values.filter((value): value is string => value !== null);
  if (known.length === 0) return null;
  return fromCents(known.reduce((total, value) => total + toCents(value), 0n));
}

/** The lines to draw, in draw order: the combined total, then the named accounts by rank, then the folded line. */
export function buildBalanceLines(series: SeriesInput, theme: Theme): BalanceLine[] {
  const names = new Map(series.accounts.map((account) => [account.accountId, account.name]));
  const ranked = rankSeriesAccounts(series);
  const named = ranked.slice(0, MAX_NAMED_ACCOUNTS);
  const folded = ranked.slice(MAX_NAMED_ACCOUNTS);

  const lines: BalanceLine[] = [
    {
      key: "combined",
      kind: "combined",
      label: "Combined total",
      color: COMBINED_COLOR[theme],
      width: 3,
      accountIds: [],
      values: series.points.map((point) => point.combinedSgd),
    },
  ];
  named.forEach((id, index) => {
    lines.push({
      key: id,
      kind: "account",
      label: names.get(id) ?? id,
      color: CATEGORICAL_PALETTE[index],
      width: 2,
      accountIds: [id],
      values: series.points.map((point) => valueAt(point, id)),
    });
  });
  if (folded.length > 0) {
    lines.push({
      key: "other",
      kind: "other",
      label: `Other accounts (${folded.length})`,
      color: OTHER_COLOR,
      width: 2,
      accountIds: folded,
      values: series.points.map((point) => sumKnown(folded.map((id) => valueAt(point, id)))),
    });
  }
  return lines;
}

/** Chart.js wants numbers; this is the one place amounts become them (plotting only, never displayed from here). */
export function toChartNumbers(values: readonly (string | null)[]): (number | null)[] {
  return values.map((value) => (value === null ? null : Number(value)));
}

export const markerRadius = (pointCount: number): number => (pointCount <= MARKER_LIMIT ? 3 : 0);

const isMonthEnd = (iso: string): boolean => addDays(iso, 1).slice(8) === "01";

/**
 * The text under each point on the axis. Daily points read "18 Oct" ("18 Oct 2025" when the range crosses a year);
 * month points read "Oct 2026", and the range's final point, when it is not a month end, reads as the day it is.
 */
export function chartLabels(series: Pick<SeriesResponse, "granularity" | "points">): string[] {
  const dates = series.points.map((point) => point.date);
  if (dates.length === 0) return [];
  const crossesYear = dates[0].slice(0, 4) !== dates[dates.length - 1].slice(0, 4);
  return dates.map((date) => {
    if (series.granularity === "day") return formatDay(date, crossesYear);
    if (!isMonthEnd(date)) return formatDay(date, true);
    return `${monthName(Number(date.slice(5, 7))).slice(0, 3)} ${date.slice(0, 4)}`;
  });
}

/** One sentence with the exact figures the chart can only show on hover. */
export function summarizeSeries(series: Pick<SeriesResponse, "points">): string {
  const known = series.points.filter((point) => point.combinedSgd !== null);
  if (known.length === 0) return "There is no combined balance in this range.";
  const first = known[0];
  const last = known[known.length - 1];
  if (known.length === 1) {
    return `The combined balance on ${formatDay(first.date, true)} is SGD ${formatAmount(first.combinedSgd)}.`;
  }
  const change = subtractAmounts(last.combinedSgd as string, first.combinedSgd as string);
  const cents = toCents(change);
  const shown = cents === 0n ? "no change" : `${cents > 0n ? "+" : "-"}SGD ${formatAmount(fromCents(cents < 0n ? -cents : cents))}`;
  return (
    `Combined balance went from SGD ${formatAmount(first.combinedSgd)} on ${formatDay(first.date, true)} ` +
    `to SGD ${formatAmount(last.combinedSgd)} on ${formatDay(last.date, true)} (${shown}).`
  );
}
