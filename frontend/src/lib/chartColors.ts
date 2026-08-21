/**
 * Validated categorical palette (8 fixed hues, fixed order -- the order is the CVD-safety
 * mechanism, never cycled/reordered per-chart). See the dataviz skill's palette.md; passed
 * `validate_palette.js` for both CVD and normal-vision separation before use here.
 */
export const CATEGORICAL_PALETTE = [
  "#2a78d6", // 1 blue
  "#eb6834", // 2 orange
  "#1baf7a", // 3 aqua
  "#eda100", // 4 yellow
  "#e87ba4", // 5 magenta
  "#008300", // 6 green
  "#4a3aa7", // 7 violet
  "#e34948", // 8 red
] as const;

export const OTHER_LABEL = "Other";
// Muted ink (chart chrome), deliberately outside the categorical hues -- a fold-in
// bucket is not a series identity, so it must not borrow one of the 8 slots.
export const OTHER_COLOR = "#898781";
// Exported so chartTheme.ts can pick the right one (light vs. dark) as the point-border
// ring color for lineMarkStyle() -- the ring must match whatever the chart is actually
// sitting on, which differs between light and dark mode.
export const SURFACE_COLOR = "#fcfcfb";

// A 9th+ series is never a generated hue (dataviz skill, non-negotiable) -- past this
// many distinct identities, the rest fold into a single "Other" bucket instead.
const MAX_NAMED_SERIES = CATEGORICAL_PALETTE.length - 1;

export interface CategoricalSeries {
  label: string;
  color: string;
  data: number[];
}

/**
 * Buckets `points` by `keyOf(point)` into series over a fixed set of `xLabels` (e.g.
 * months), summing `valueOf(point)` per bucket per x-label. Ranks buckets by total
 * value and keeps only the top MAX_NAMED_SERIES; any remainder is summed into a
 * single "Other" series colored OTHER_COLOR, rather than generating additional
 * ad-hoc hues once the validated palette's slots run out.
 */
export function buildCategoricalSeries<T>(
  points: T[],
  xLabels: string[],
  xOf: (point: T) => string,
  keyOf: (point: T) => string,
  valueOf: (point: T) => number,
): CategoricalSeries[] {
  const totalByKey = new Map<string, number>();
  const valueByKeyAndX = new Map<string, Map<string, number>>();

  for (const point of points) {
    const key = keyOf(point);
    const x = xOf(point);
    const value = valueOf(point);
    totalByKey.set(key, (totalByKey.get(key) ?? 0) + value);
    if (!valueByKeyAndX.has(key)) valueByKeyAndX.set(key, new Map());
    const byX = valueByKeyAndX.get(key)!;
    byX.set(x, (byX.get(x) ?? 0) + value);
  }

  const ranked = Array.from(totalByKey.entries()).sort((a, b) => b[1] - a[1]);
  const namedKeys = ranked.slice(0, MAX_NAMED_SERIES).map(([key]) => key);
  const overflowKeys = ranked.slice(MAX_NAMED_SERIES).map(([key]) => key);

  const series: CategoricalSeries[] = namedKeys.map((key, i) => ({
    label: key,
    color: CATEGORICAL_PALETTE[i],
    data: xLabels.map((x) => valueByKeyAndX.get(key)?.get(x) ?? 0),
  }));

  if (overflowKeys.length > 0) {
    series.push({
      label: OTHER_LABEL,
      color: OTHER_COLOR,
      data: xLabels.map((x) => overflowKeys.reduce((sum, key) => sum + (valueByKeyAndX.get(key)?.get(x) ?? 0), 0)),
    });
  }

  return series;
}

/** Mark spec for a bar/column series (dataviz skill: capped thickness, rounded data-end). */
export function barMarkStyle(color: string) {
  return {
    backgroundColor: color,
    borderRadius: 4,
    borderSkipped: "bottom" as const,
    maxBarThickness: 24,
  };
}

/** Mark spec for a line series (dataviz skill: 2px line, >=8px point with a surface ring).
 * `surfaceColor` defaults to the light-mode chart background (SURFACE_COLOR) but must be
 * passed explicitly as the dark-mode surface color when the chart is rendered in dark
 * mode -- otherwise the point-border ring stays near-white against a dark background. */
export function lineMarkStyle(color: string, surfaceColor: string = SURFACE_COLOR) {
  return {
    borderColor: color,
    backgroundColor: color,
    borderWidth: 2,
    pointRadius: 4,
    pointBorderColor: surfaceColor,
    pointBorderWidth: 2,
    tension: 0.2,
  };
}
