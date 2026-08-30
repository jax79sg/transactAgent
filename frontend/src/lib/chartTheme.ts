import type { ChartOptions, ChartType } from "chart.js";

import type { Theme } from "../context/ThemeContext";
import { SURFACE_COLOR } from "./chartColors";

/** Matches ProtectedLayout's `dark:bg-slate-950` page background -- the surface every
 * chart actually sits on in dark mode, used both as the point-border ring color
 * (lineMarkStyle) and as the basis for chart chrome colors below. */
const DARK_SURFACE_COLOR = "#020617";

const LIGHT_TICK_COLOR = "#475569"; // slate-600, Chart.js's own default is close to this
const DARK_TICK_COLOR = "#cbd5e1"; // slate-300 -- legible on the dark surface, not stark white

const LIGHT_GRID_COLOR = "rgba(15, 23, 42, 0.1)"; // slate-900 at low opacity
const DARK_GRID_COLOR = "rgba(203, 213, 225, 0.15)"; // slate-300 at low opacity

/** Theme-aware Chart.js option fragments (axis ticks/gridlines, legend text) plus the
 * point-border surface color lineMarkStyle() needs -- chart chrome only. The validated
 * categorical palette (CATEGORICAL_PALETTE) itself never changes between themes.
 * Generic over the chart type (each of react-chartjs-2's <Bar>/<Line> wants its own
 * specific ChartOptions<"bar">/ChartOptions<"line">, not a "bar" | "line" union) --
 * callers pass the type explicitly, e.g. getChartTheme<"bar">(theme). */
export function getChartTheme<T extends ChartType = "bar">(theme: Theme): { options: ChartOptions<T>; surfaceColor: string } {
  const tickColor = theme === "dark" ? DARK_TICK_COLOR : LIGHT_TICK_COLOR;
  const gridColor = theme === "dark" ? DARK_GRID_COLOR : LIGHT_GRID_COLOR;

  return {
    surfaceColor: theme === "dark" ? DARK_SURFACE_COLOR : SURFACE_COLOR,
    options: {
      // Without an explicit height + maintainAspectRatio: false, Chart.js sizes the
      // canvas off its default aspect ratio rather than shrinking to the actual
      // viewport width, which is what caused the dashboard to overflow horizontally
      // on narrow mobile screens (issue #19) -- pairs with each chart's h-* wrapper.
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: tickColor }, grid: { color: gridColor } },
        y: { ticks: { color: tickColor }, grid: { color: gridColor } },
      },
      plugins: {
        legend: { labels: { color: tickColor } },
      },
    } as ChartOptions<T>,
  };
}
