# Dark Mode — Requirements

## Intent Analysis Summary

- **User Request**: GitHub issue #1 ("Need a dark mode") — "The current theme is not pleasant for my group of users. Please create a dark mode."
- **Request Type**: New Feature (Enhancement)
- **Scope Estimate**: Multiple Components — Frontend SPA only (NavBar, all 7 pages and their inline sub-components, Chart.js charts on the Dashboard). No Database/API Service/Ingestion Worker Service changes; this is purely a client-side presentation concern.
- **Complexity Estimate**: Moderate — no new backend surface or data model, but the app currently has zero dark-mode styling (plain Tailwind, no `dark:` variants, no theme config anywhere), so every page/component needs a styling pass, and a genuine design/contrast review is in scope per the user's answer to Q5.

## Functional Requirements

- **FR-DM-1**: The application shall support two visual modes: Light and Dark.
- **FR-DM-2**: On first load (no stored preference yet), the application shall default to the user's OS/browser preference via the `prefers-color-scheme` media query.
- **FR-DM-3**: The application shall provide a manual toggle control, located in the NavBar (always visible), that lets the user switch between Light and Dark mode regardless of OS preference.
- **FR-DM-4**: Once the user manually toggles the mode, that explicit choice shall take precedence over the OS preference for all subsequent visits on that browser (i.e. manual choice overrides, and persists across, the OS-preference default).
- **FR-DM-5**: The chosen mode shall persist across browser sessions via `localStorage` (per-device; no backend/account storage).
- **FR-DM-6**: Dark mode shall apply across the entire application: NavBar, all 7 pages (`DashboardPage`, `TransactionsPage`, `ReviewPage`, `IngestionPage`, `SettingsPage`, `AskAiPage`, `LoginPage`), and every inline sub-component within them (tables, dialogs, badges/status pills, panels, zebra striping, etc.).
- **FR-DM-7**: The Dashboard's Chart.js charts shall also be visually adapted for dark mode (axis/gridline/label colors, tooltip styling, legend text) — not left rendering in a light-only style when the app is in dark mode.
- **FR-DM-8**: If a user has multiple browser tabs/windows of the app open, changing the mode in one tab shall be reflected in the others (standard `localStorage`/`storage`-event propagation), consistent with how the app already behaves for other client-side state.

## Non-Functional Requirements

- **NFR-DM-1 (Visual Quality)**: This is a "polished pass," not just a mechanical light→dark palette swap. Colors, backgrounds, borders, and status/accent colors in dark mode must be deliberately chosen for legibility and a reasonable dark-UI aesthetic — not merely inverted or reused as-is from light mode.
- **NFR-DM-2 (Accessibility/Contrast)**: Text-to-background contrast in dark mode should meet WCAG AA (≥4.5:1 for normal text, ≥3:1 for large text/UI components) for primary content. Status colors (success/warning/error/pending badges etc.) must remain visually distinguishable from one another in dark mode.
- **NFR-DM-3 (No Flash of Wrong Theme - FOUC)**: The correct mode (from stored preference or OS default) should be applied before/at initial paint, avoiding a visible flash of the wrong theme on page load.
- **NFR-DM-4 (No New Design System)**: Implementation should extend the existing Tailwind setup (via `darkMode: 'class'` + `dark:` variants) rather than introducing a separate theming library or CSS-in-JS system. No preference on exact color values was given — implementer's judgment applies (common dark-UI convention: dark-slate/near-black backgrounds rather than pure black, light-gray text, muted borders).
- **NFR-DM-5 (No Regression)**: Existing light-mode appearance must remain visually unchanged (pixel-equivalent look/feel) — this feature adds a mode, it does not redesign the light theme.
- **NFR-DM-6 (Test Coverage)**: The mode-toggle logic (OS-preference detection, manual override, `localStorage` persistence, cross-tab sync) should have unit test coverage, consistent with this project's existing frontend testing conventions.

## Answers to Clarifying Questions (source of truth)

| # | Question (short) | Answer |
|---|---|---|
| 1 | Toggle behavior | C — Default to OS preference, manual toggle can override |
| 2 | Toggle placement | A — NavBar |
| 3 | Persistence | A — `localStorage`, per-device |
| 4 | Scope | A — Entire app, including Chart.js charts |
| 5 | Quality bar | B — Polished pass (deliberate contrast/color design review) |
| 6 | Palette constraints | A — No preference, use judgment |

## Summary

Add a Light/Dark mode toggle to the NavBar, defaulting to the OS preference and falling back to a persisted manual choice in `localStorage` once the user overrides it. Scope is the entire Frontend SPA — every page, inline sub-component, and the Dashboard's Chart.js charts — implemented via Tailwind's `dark:` variant strategy (`darkMode: 'class'`), with no backend, database, or API changes. The bar is a genuine design pass (WCAG AA contrast, distinguishable status colors) rather than a mechanical color inversion, while leaving the existing light theme visually unchanged.
