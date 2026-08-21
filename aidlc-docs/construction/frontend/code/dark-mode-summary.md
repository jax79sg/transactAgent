# Dark Mode — Code Summary (Epic 12)

Source: GitHub issue #1. Frontend SPA only — no Database/API Service/Ingestion Worker Service changes.

## Approach

Tailwind's `class` dark-mode strategy (`darkMode: 'class'`), not the `media` default —
the app needs to control the mode itself (OS-default + manual override + persistence),
not just mirror `prefers-color-scheme` directly.

- **Initial mode, no flash (NFR-DM-3)**: a small inline `<script>` in `index.html`'s
  `<head>`, before any stylesheet/app script, reads `localStorage`'s
  `transactagent_theme` key if present, else falls back to
  `matchMedia('(prefers-color-scheme: dark)')`, and sets `.dark` on `<html>`
  synchronously, before React ever mounts.
- **State/behavior**: new `src/context/ThemeContext.tsx` (`ThemeProvider` + `useTheme()`,
  modeled on `AuthContext.tsx`'s conventions). Resolves the same way the inline script
  did on mount (and re-applies it defensively via its own effect, so the provider is
  correct even without `index.html`'s script — e.g. in tests). A manual `setTheme`/
  `toggleTheme` call persists to `localStorage` and from then on takes precedence over
  the OS preference; until an explicit choice exists, a `matchMedia` change listener
  keeps following the live OS preference. A `storage` event listener syncs a toggle made
  in one tab to every other open tab.
- **Styling**: a `dark:` variant pass across every existing hardcoded light-mode color
  utility — NavBar, `ProtectedLayout`, `ErrorBoundary`, and all 7 pages (~130 existing
  `slate`/`white` utility occurrences extended, plus status colors like `amber`/`red`/
  `blue`/`green` badges). The existing light-mode classes are untouched (NFR-DM-5 — no
  regression). Radix `Portal`-rendered content (`Dialog.Content`, `Select.Content`) needed
  its own explicit dark background/text, since portals mount outside `<main>`'s ancestor
  chain and don't inherit its base dark text color.
- **Charts**: new `src/lib/chartTheme.ts` (`getChartTheme<T>(theme)`) returns theme-aware
  Chart.js option fragments (axis tick/gridline color, legend text color) and a
  `surfaceColor`. `chartColors.ts`'s `lineMarkStyle()` now takes the surface color as a
  parameter (was a hardcoded near-white constant) so a line chart's point-border ring
  matches whichever background the chart is actually sitting on. The validated
  categorical palette (`CATEGORICAL_PALETTE`) is unchanged in both modes.

## Files Created

- `frontend/src/context/ThemeContext.tsx`
- `frontend/src/lib/chartTheme.ts`
- `frontend/tests/ThemeContext.test.tsx`

## Files Modified

- `frontend/tailwind.config.js` — `darkMode: 'class'`
- `frontend/index.html` — FOUC-prevention inline script
- `frontend/src/main.tsx` — wired in `ThemeProvider`
- `frontend/src/components/NavBar.tsx` — `ThemeToggle` control + dark styling
- `frontend/src/components/ProtectedLayout.tsx` — dark styling
- `frontend/src/components/ErrorBoundary.tsx` — dark styling
- `frontend/src/pages/LoginPage.tsx` — dark styling
- `frontend/src/pages/AskAiPage.tsx` — dark styling
- `frontend/src/pages/IngestionPage.tsx` — dark styling
- `frontend/src/pages/TransactionsPage.tsx` — dark styling
- `frontend/src/pages/ReviewPage.tsx` — dark styling
- `frontend/src/pages/SettingsPage.tsx` — dark styling
- `frontend/src/pages/DashboardPage.tsx` — dark styling + chart theming wiring
- `frontend/src/lib/chartColors.ts` — `lineMarkStyle()` surface-color parameter, `SURFACE_COLOR` exported
- `frontend/tests/NavBar.test.tsx` — theme toggle test coverage, `ThemeProvider` added to render helper
- `frontend/tests/DashboardPage.test.tsx` — `ThemeProvider` added to render helper (now required, `DashboardPage` calls `useTheme()`)
- `frontend/tests/setup.ts` — global `matchMedia` polyfill (jsdom doesn't implement it)

## Verification

- `tsc -b`: clean
- `eslint .`: clean (0 errors; pre-existing-pattern warnings only, same as `AuthContext.tsx`)
- `vitest run`: 110/110 passing (up from 99 — 8 new `ThemeContext` tests, 3 new NavBar toggle tests)
- `vite build`: clean production build
