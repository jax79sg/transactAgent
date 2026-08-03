# Functional Design Plan — Unit 4: Frontend SPA

**Input**: `unit-of-work.md` (Unit 4 definition), `unit-of-work-story-map.md` (all 24 stories — Frontend implements the UI for every one), `api-service/functional-design/domain-entities.md` (the DTO/API contract this unit consumes), `api-service/code/api-layer-summary.md` (actual endpoint list, including `/drive/*`)

## Unit Context

Unit 4 is the only unit with a UI. It depends solely on Unit 2's REST API (never talks to Unit 1 or Unit 3 directly). This Functional Design covers component structure, state, user interaction flows, form validation, and API integration points — framework-agnostic (the specific framework, e.g. React vs. Vue, is an NFR Requirements tech-stack decision, not decided here).

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (JWT storage location, page/route structure, inline vs. modal category correction) — sessionStorage, 5-page structure, inline correction
- [x] Step 2: Generate `frontend-components.md` — component hierarchy, props/state, user interaction flows, form validation rules, API integration points per component
- [x] Step 3: Generate `business-logic-model.md` — session lifecycle, run-status polling lifecycle, filter/group URL-state mapping, drill-down, CSV export, category cache
- [x] Step 4: Cross-check every story is covered by at least one component — all 24 stories map to the 5 pages; no gaps

## Clarifying Questions

### Question 1 — JWT Storage Location
Where should the frontend store the JWT after login?

A) **`localStorage`** — persists across browser restarts/tabs (no need to log in again after closing the browser), but is readable by any JS running on the page (XSS exposure) — acceptable risk for a personal, non-public app with no third-party scripts

B) **In-memory only** (a JS variable, lost on page refresh) — most XSS-resistant, but you'd need to log in again every time you reload the page, which is poor UX for a personal app you check periodically

C) **`sessionStorage`** — a middle ground: persists across reloads within the same tab, but cleared when the tab/browser closes

X) Other (please describe after [Answer]: tag below)

[Answer]: C

### Question 2 — Page/Route Structure
Proposed pages, one per major capability:

- **Login** (`/login`)
- **Dashboard** (`/`) — the 3 insight views (category trends, cash flow, bank breakdown) as tabs or sections on one page
- **Transactions** (`/transactions`) — the filterable/groupable table, manual correction, CSV export, UNSURE shortcut filter
- **Ingestion** (`/ingestion`) — trigger button, live run progress, run history with drill-down to per-file outcomes
- **Settings** (`/settings`) — category whitelist management, Google Drive connection status/connect button (redirect target for `/drive/callback`)

Does this page structure match how you'd want to navigate the app, or would you organize it differently?

A) Yes, use this 5-page structure as proposed

B) Different structure — describe below

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3 — Manual Category Correction UX
When correcting a transaction's category in the table (US-3.4), should the category selector appear inline in the row, or in a separate modal/dialog?

A) **Inline** — a dropdown/select directly in the table row's category cell, click to edit in place — fast for correcting many transactions in a row

B) **Modal/dialog** — clicking "correct" opens a small dialog with the category picker and a confirm button — clearer separation of "viewing" vs. "editing" mode, slightly slower for bulk corrections

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
