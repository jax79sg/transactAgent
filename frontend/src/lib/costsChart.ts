import type { CostGranularity, CostGroupBy, CostsResponse } from "../api/types";
import { CATEGORICAL_PALETTE, OTHER_COLOR, OTHER_LABEL } from "./chartColors";

/** What each recorded purpose is called on the page. */
export const PURPOSE_LABELS: Record<string, string> = {
  statement_extraction: "Statement extraction",
  categorization: "Categorization",
  embedding: "Embeddings",
  ask_ai: "Ask AI",
};

// Color follows the entity, never its rank (dataviz skill): the four purposes always wear the same hue, whatever
// the range or the other purposes present -- a filter must not repaint the survivors.
const PURPOSE_ORDER = ["statement_extraction", "categorization", "embedding", "ask_ai"];

const MAX_NAMED_SERIES = CATEGORICAL_PALETTE.length - 1;

export function groupLabel(group: string, groupBy: CostGroupBy): string {
  return groupBy === "purpose" ? (PURPOSE_LABELS[group] ?? group) : group;
}

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Spelled out here rather than taken from Intl: the exact punctuation of a locale-formatted date ("Mon, 5 Oct" or
// "Mon 5 Oct") differs between engines and ICU versions, and a label that changes with the browser is a label
// nobody can test. A calendar day has no time zone, so this works on the date's own parts and cannot shift a day.
function parts(isoDay: string): { year: number; month: number; day: number; weekday: number } {
  const [year, month, day] = isoDay.split("-").map(Number);
  return { year, month: month - 1, day, weekday: new Date(Date.UTC(year, month - 1, day)).getUTCDay() };
}

/** Short label for a chart axis. */
export function axisLabel(period: string, granularity: CostGranularity): string {
  const { year, month, day } = parts(period);
  if (granularity === "month") return `${MONTHS_SHORT[month]} ${year}`;
  const text = `${day} ${MONTHS_SHORT[month]}`;
  return granularity === "week" ? `Wk ${text}` : text;
}

/** Full label for a table row or tooltip. */
export function periodLabel(period: string, granularity: CostGranularity): string {
  const { year, month, day, weekday } = parts(period);
  if (granularity === "month") return `${MONTHS_LONG[month]} ${year}`;
  const text = `${day} ${MONTHS_SHORT[month]} ${year}`;
  return granularity === "week" ? `Week of ${text}` : `${WEEKDAYS_SHORT[weekday]} ${text}`;
}

export interface CostDataset {
  group: string;
  label: string;
  color: string;
  /** One cost (US dollars) per period of the response, zero where there was no spend. */
  data: number[];
}

function colorFor(group: string, groupBy: CostGroupBy, rank: number): string {
  if (groupBy === "purpose") {
    const index = PURPOSE_ORDER.indexOf(group);
    if (index >= 0) return CATEGORICAL_PALETTE[index];
  }
  return CATEGORICAL_PALETTE[rank];
}

/** One dataset per group, over every period of the response (zero-filled). Groups arrive most expensive first;
 * past the palette's named slots the rest fold into one "Other" bucket instead of generating more hues. */
export function buildCostDatasets(response: CostsResponse): CostDataset[] {
  const byGroupAndPeriod = new Map<string, Map<string, number>>();
  for (const point of response.series) {
    if (!byGroupAndPeriod.has(point.group)) byGroupAndPeriod.set(point.group, new Map());
    byGroupAndPeriod.get(point.group)!.set(point.period, Number(point.costUsd));
  }
  const valuesOf = (group: string) => response.periods.map((p) => byGroupAndPeriod.get(group)?.get(p) ?? 0);

  const named = response.groupBy === "purpose" ? response.groups : response.groups.slice(0, MAX_NAMED_SERIES);
  const overflow = response.groupBy === "purpose" ? [] : response.groups.slice(MAX_NAMED_SERIES);

  const datasets: CostDataset[] = named.map((g, rank) => ({
    group: g.group,
    label: groupLabel(g.group, response.groupBy),
    color: colorFor(g.group, response.groupBy, rank),
    data: valuesOf(g.group),
  }));
  if (overflow.length > 0) {
    const rest = overflow.map((g) => valuesOf(g.group));
    datasets.push({
      group: OTHER_LABEL,
      label: OTHER_LABEL,
      color: OTHER_COLOR,
      data: response.periods.map((_, i) => rest.reduce((sum, values) => sum + values[i], 0)),
    });
  }
  return datasets;
}

export interface PeriodRow {
  period: string;
  costUsd: number;
  calls: number;
  inputTokens: number;
  outputTokens: number;
}

/** One row per period that had calls, summed across groups. */
export function buildPeriodRows(response: CostsResponse): PeriodRow[] {
  const rows = new Map<string, PeriodRow>();
  for (const point of response.series) {
    const row = rows.get(point.period) ?? { period: point.period, costUsd: 0, calls: 0, inputTokens: 0, outputTokens: 0 };
    row.costUsd += Number(point.costUsd);
    row.calls += point.calls;
    row.inputTokens += point.inputTokens;
    row.outputTokens += point.outputTokens;
    rows.set(point.period, row);
  }
  return Array.from(rows.values());
}

export type SortDirection = "asc" | "desc";

/** Sorts a copy of `rows` by a numeric or string key; ties keep a stable, readable order via `tiebreak`. */
export function sortRows<T, K extends keyof T>(rows: T[], key: K, dir: SortDirection, tiebreak: keyof T): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    const primary = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    if (primary !== 0) return sign * primary;
    return String(a[tiebreak]).localeCompare(String(b[tiebreak]));
  });
}
