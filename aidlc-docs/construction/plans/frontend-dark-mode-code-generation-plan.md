# Code Generation Plan — Frontend SPA: Dark Mode (Epic 12)

**Unit**: Frontend SPA (only unit affected — Database/API Service/Ingestion Worker Service untouched)
**Workspace root**: `/Users/jax/projects/transactAgent` (per `aidlc-docs/aidlc-state.md`)
**Application code location**: `frontend/` (existing project structure — brownfield, modify in place)
**Stories implemented**: US-12.1, US-12.2, US-12.3, US-12.4 (`dark-mode-stories.md`, Epic 12)
**Dependencies**: None — no API/DB calls involved; purely client-side state + Tailwind CSS

## Current-State Findings (informs the steps below)
- `frontend/tailwind.config.js` has no `darkMode` strategy configured (defaults to `media`, not controllable) and no theme extension.
- `frontend/index.html` has no FOUC-prevention script — needed per NFR-DM-3.
- `frontend/src/main.tsx` is the top-level provider stack (`ErrorBoundary` → `QueryClientProvider` → `App`); `frontend/src/App.tsx` wraps `AuthProvider` → `BrowserRouter`.
- No existing theme/dark-mode code anywhere. Color usage today is Tailwind's `slate` scale + `white` almost exclusively (~130 occurrences across `NavBar.tsx`, `ProtectedLayout.tsx`, `ErrorBoundary.tsx`, and all 7 pages), plus saturated status colors (`amber-500`, `emerald-500/700`, etc.) for badges/pills — the slate scale itself spans light↔dark, making a systematic `dark:` inversion straightforward.
- Dashboard charts (`DashboardPage.tsx`, via `react-chartjs-2`) get no per-chart theming today (Chart.js defaults: black-ish text/gridlines) — `src/lib/chartColors.ts`'s `lineMarkStyle()` hardcodes a near-white `SURFACE_COLOR` for point-border rings, which would look wrong on a dark background.
- Tests live in `frontend/tests/` (not colocated with `src/`), use Vitest + Testing Library, mock API modules with `vi.mock`/`vi.spyOn`. `frontend/tests/setup.ts` is the global test setup file.

## Steps

- [x] **Step 1 — Tailwind dark-mode strategy**
  Modify `frontend/tailwind.config.js`: add `darkMode: 'class'` so dark mode is driven by a `.dark` class on `<html>`, not the OS media query directly (the app controls it via `ThemeContext`, not Tailwind).

- [x] **Step 2 — FOUC-prevention script**
  Modify `frontend/index.html`: add a small synchronous inline `<script>` in `<head>`, before any stylesheet/app script, that reads the `localStorage` theme key if present, else falls back to `window.matchMedia('(prefers-color-scheme: dark)')`, and sets `document.documentElement.classList` accordingly — so the correct mode is applied at first paint (NFR-DM-3), before React mounts.

- [x] **Step 3 — ThemeContext (business/state logic)**
  Create `frontend/src/context/ThemeContext.tsx`: `ThemeProvider` + `useTheme()` hook, modeled on `AuthContext.tsx`'s conventions.
  - Reads initial state the same way the inline script computed it (stored `localStorage` value if present, else OS preference via `matchMedia`).
  - Exposes `{ theme: 'light' | 'dark', setTheme, toggleTheme }`.
  - On manual `setTheme`/`toggleTheme`: writes the explicit choice to `localStorage` (key: `transactagent_theme`) and updates `document.documentElement`'s `dark` class — this explicit choice now takes precedence over OS preference (FR-DM-4).
  - While no explicit choice has ever been stored: subscribes to the `matchMedia` change event so the app keeps following the live OS preference (FR-DM-2).
  - Subscribes to the `storage` event so a change made in another tab updates this tab's state and DOM class without a manual refresh (FR-DM-8).

- [x] **Step 4 — Wire ThemeProvider into the app**
  Modify `frontend/src/main.tsx`: add `ThemeProvider` to the top-level provider stack (outside `QueryClientProvider`/`App`, no dependency on auth or query state).

- [x] **Step 5 — NavBar toggle + dark styling**
  Modify `frontend/src/components/NavBar.tsx`:
  - Add a `ThemeToggle` control (button, `data-testid="theme-toggle"`) next to the existing `ActivityIndicator`/logout button, using `useTheme()`. Clearly indicates current mode (e.g. sun/moon icon or explicit "Light"/"Dark" label — not an ambiguous icon-only toggle).
  - Add `dark:` variants to the NavBar's own classes (background, border, link text/active states, existing badges).

- [x] **Step 6 — Shell components dark styling**
  Modify `frontend/src/components/ProtectedLayout.tsx` and `frontend/src/components/ErrorBoundary.tsx`: add `dark:` variants (background, text, button).

- [x] **Step 7 — Page-by-page dark styling pass**
  Modify all 7 pages, adding `dark:` variants to every hardcoded light-mode color utility (backgrounds, text, borders, table zebra striping, dialogs/panels, status badges/pills where contrast requires it) while leaving the existing light-mode classes untouched (NFR-DM-5 — no regression):
  - `frontend/src/pages/LoginPage.tsx`
  - `frontend/src/pages/AskAiPage.tsx`
  - `frontend/src/pages/IngestionPage.tsx`
  - `frontend/src/pages/TransactionsPage.tsx`
  - `frontend/src/pages/ReviewPage.tsx`
  - `frontend/src/pages/SettingsPage.tsx`
  - `frontend/src/pages/DashboardPage.tsx` (styling only in this step — chart theming is Step 8)

- [x] **Step 8 — Chart.js dark theming**
  - Create `frontend/src/lib/chartTheme.ts`: exports a `getChartTheme(theme: 'light' | 'dark')` helper returning theme-aware Chart.js option fragments (axis tick/label color, gridline color, legend text color, tooltip background/text color) and a `surfaceColor` (replaces `chartColors.ts`'s hardcoded near-white `SURFACE_COLOR` for point-border rings when dark).
  - Modify `frontend/src/lib/chartColors.ts`: `lineMarkStyle()` accepts the theme-appropriate surface color as a parameter instead of the hardcoded constant.
  - Modify `frontend/src/pages/DashboardPage.tsx`: read `useTheme()`, merge `getChartTheme(theme)`'s options into each `Bar`/`Line` chart's existing `options`, and pass the themed surface color into `lineMarkStyle` calls. The validated categorical palette (`CATEGORICAL_PALETTE`) itself is unchanged — only chart chrome (axes/gridlines/legend/tooltip/point-ring) is theme-aware.

- [x] **Step 9 — Frontend unit tests: ThemeContext**
  Create `frontend/tests/ThemeContext.test.tsx`: covers OS-preference default (mocking `matchMedia`), manual override precedence over OS preference, `localStorage` persistence across a simulated reload, and cross-tab sync via a dispatched `storage` event — matching this project's existing Vitest/Testing Library conventions.

- [x] **Step 10 — Frontend unit tests: NavBar toggle**
  Modify `frontend/tests/NavBar.test.tsx`: add a `describe("NavBar theme toggle")` block covering — toggle renders and shows current mode; clicking it switches mode and updates `document.documentElement`'s class; existing badge/activity tests remain unaffected (wrap `renderNavBar()` in `ThemeProvider` alongside the existing providers).

- [x] **Step 11 — Documentation summary**
  Create `aidlc-docs/construction/frontend/code/dark-mode-summary.md`: lists files created/modified, the theming approach (Tailwind `class` strategy + `ThemeContext`), and the chart-theming approach — markdown only, per Code Location Rules.

## Story Traceability
| Step | Stories Covered |
|---|---|
| 1–4 | US-12.1, US-12.3 |
| 5 | US-12.2, US-12.3 |
| 6, 7 | US-12.4 |
| 8 | US-12.4 (charts) |
| 9, 10 | US-12.1, US-12.2, US-12.3 (behavioral coverage) |
| 11 | — (documentation) |
