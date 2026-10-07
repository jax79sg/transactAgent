# Unit 4: Frontend SPA — Package Overview

React + TypeScript SPA, built with Vite, served in production by nginx. Talks only to Unit 2's REST API — no dependency on Unit 1's `database` package.

## Running Locally (development)

```bash
cd frontend
npm install
npm run dev
```

Opens on Vite's dev server (default `http://localhost:5173`); `config.ts` falls back to `http://localhost:7878` for the API base URL in dev (no `config.js` exists outside a built container). Requires Unit 2 (and, for the OAuth flow, Unit 2's Google OAuth client configured) running separately.

## Running Tests

```bash
npm install
npm test          # vitest run — unit + component tests, and the fast-check PBT suite
npm run build      # tsc type-check + production build
```

No live backend or Docker needed — all API calls in tests are mocked.

## Structure

```
frontend/src/
  main.tsx, App.tsx        # entrypoint, routing, providers
  config.ts                 # runtime config (window.__APP_CONFIG__)
  api/                        # client.ts (fetch wrapper, camelCase->snake_case query
                               #   conversion, centralized 401 handling), types.ts, and
                               #   one file per domain (auth, transactions, dashboards,
                               #   ingestion, categories, driveConnect, recategorization,
                               #   duplicates)
  context/AuthContext.tsx      # session state (sessionStorage)
  components/                   # ErrorBoundary, NavBar (incl. PendingReviewBadge and
                                  #   PendingDuplicatesBadge), ProtectedLayout,
                                  #   DuplicateStatementsPanel (Review page, Epic 14)
  pages/                          # LoginPage, DashboardPage, TransactionsPage,
                                  #   IngestionPage, ReviewPage, SettingsPage,
                                  #   ComparisonPage (/duplicates/:comparisonId, Epic 14)
  lib/
    urlFilterState.ts             # pure filter-state <-> URL round-trip (PBT target)
    chartSetup.ts                  # Chart.js component registration
    duplicates.ts                   # statement labels, period text, duplicate error messages (Epic 14)
```

## Key Design Notes (resolved during Code Generation)

- **Query params are snake_case**: Unit 2's GET endpoints use plain FastAPI `Query`/`BaseModel` params (`date_from`, `page_size`), not the camelCase used by JSON bodies/responses. `api/client.ts`'s `buildUrl()` converts camelCase JS keys to snake_case centrally so every caller can stay idiomatic TS.
- **CSV export is fetch+Blob, not `<a href>`**: the export endpoint requires the same JWT as everything else; a plain browser navigation has no way to attach an `Authorization` header.
- **Probable duplicate statements (Epic 14)**: see `probable-duplicate-summary.md`. The panel only ever *requests* a removal (the worker re-verifies and executes); a confirmation carries the hash of the copy and the exact correction count it showed. Every action invalidates the `["duplicates"]` query prefix, so the list, the nav badge and the scan status refresh together. Enumerated settings (the first being the duplicate-detection switch) render as a dropdown.
- **Running the tests without Node on the host**: `docker run --rm -v "$PWD":/app -w /app node:20-alpine sh -c "npx vitest run"` (likewise `npx tsc --noEmit`, `npx eslint .`) from `frontend/`; the existing `node_modules` holds Linux ARM binaries.
