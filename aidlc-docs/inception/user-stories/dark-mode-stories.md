# User Stories — Dark Mode

Appends **Epic 12** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7, `recurring-payments-stories.md` Epic 8, `embedding-similarity-stories.md` Epic 9, `configurable-app-settings-stories.md` Epic 10, `background-process-visibility-stories.md` Epic 11), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then + edge cases — matches the existing convention.
**Traceability**: Each story references `dark-mode-requirements.md`'s FR-DM/NFR-DM IDs.

---

## Epic 12: Dark Mode

### US-12.1: The app opens in the right mode automatically
**As** the Account Owner, **I want** the app to open in dark or light mode matching my OS/browser setting **so that** I get a comfortable experience with zero configuration on first use.

**Traces to**: FR-DM-2, NFR-DM-3

**Acceptance Criteria**:
- *Happy path — OS is dark*: Given my OS/browser preference is dark and I have no stored preference yet, When I load the app, Then it renders in dark mode.
- *Happy path — OS is light*: Given my OS/browser preference is light and I have no stored preference yet, When I load the app, Then it renders in light mode.
- *No flash*: Given either OS preference, When the page loads, Then the correct mode is applied before/at first paint — no visible flash of the wrong theme.

### US-12.2: I can manually switch modes from anywhere in the app
**As** the Account Owner, **I want** a toggle in the NavBar that switches between light and dark mode **so that** I can override the OS default whenever I want, regardless of what page I'm on.

**Traces to**: FR-DM-1, FR-DM-3, FR-DM-4

**Acceptance Criteria**:
- *Happy path*: Given I'm on any page of the app, When I click the NavBar toggle, Then the entire app immediately switches to the other mode.
- *Override precedence*: Given my OS preference is light but I've previously chosen dark manually, When I revisit the app, Then it opens in dark mode — my manual choice wins over the OS default.
- *Visible state*: Given the toggle is present in the NavBar, When I look at it, Then it clearly indicates which mode is currently active (not just an ambiguous icon).

### US-12.3: My mode choice is remembered next time
**As** the Account Owner, **I want** my chosen mode to persist across browser sessions **so that** I don't have to re-toggle it every time I open the app.

**Traces to**: FR-DM-5, FR-DM-8

**Acceptance Criteria**:
- *Happy path*: Given I manually set dark mode, When I close the tab and reopen the app later, Then it still loads in dark mode.
- *Cross-tab sync*: Given I have two tabs of the app open at once, When I toggle mode in one tab, Then the other tab updates to match without a manual refresh.
- *Edge case — different device*: Given the preference is stored per-browser (`localStorage`), When I log in from a different device or browser, Then the mode preference does not carry over and the app falls back to that device's OS preference — this is expected behavior, not a defect, per FR-DM-5.

### US-12.4: Every screen looks intentional in dark mode, not half-finished
**As** the Account Owner, **I want** dark mode to apply consistently across every page, table, dialog, badge, and the Dashboard's charts **so that** nothing looks broken, washed-out, or forgotten when I switch modes.

**Traces to**: FR-DM-6, FR-DM-7, NFR-DM-1, NFR-DM-2, NFR-DM-5

**Acceptance Criteria**:
- *Happy path — pages*: Given dark mode is active, When I visit the Dashboard, Transactions, Review, Ingestion, Settings, Ask AI, and Login pages, Then each renders with a consistent dark palette and no leftover light-mode backgrounds or unreadable text.
- *Happy path — charts*: Given dark mode is active, When I view the Dashboard's Chart.js charts, Then axis labels, gridlines, legend text, and tooltips are all legible against the dark background.
- *Contrast*: Given dark mode is active, When I read body text and status badges/pills (e.g. pending/approved/rejected states), Then contrast meets WCAG AA and each status remains visually distinguishable from the others.
- *No regression*: Given light mode is active (whether by default or by manual choice), When I view any page, Then it looks exactly as it did before this feature shipped.

---

## Traceability Summary

| Story | Requirements Covered |
|---|---|
| US-12.1 | FR-DM-2, NFR-DM-3 |
| US-12.2 | FR-DM-1, FR-DM-3, FR-DM-4 |
| US-12.3 | FR-DM-5, FR-DM-8 |
| US-12.4 | FR-DM-6, FR-DM-7, NFR-DM-1, NFR-DM-2, NFR-DM-5 |

NFR-DM-4 (extend existing Tailwind setup, no new theming library) and NFR-DM-6 (unit test coverage for toggle logic) are cross-cutting implementation constraints reflected across all four stories rather than a dedicated story of their own.
