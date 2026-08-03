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
                               #   ingestion, categories, driveConnect, recategorization)
  context/AuthContext.tsx      # session state (sessionStorage)
  components/                   # ErrorBoundary, NavBar (incl. PendingReviewBadge), ProtectedLayout
  pages/                          # LoginPage, DashboardPage, TransactionsPage,
                                  #   IngestionPage, ReviewPage, SettingsPage
  lib/
    urlFilterState.ts             # pure filter-state <-> URL round-trip (PBT target)
    chartSetup.ts                  # Chart.js component registration
```

## Key Design Notes (resolved during Code Generation)

- **Query params are snake_case**: Unit 2's GET endpoints use plain FastAPI `Query`/`BaseModel` params (`date_from`, `page_size`), not the camelCase used by JSON bodies/responses. `api/client.ts`'s `buildUrl()` converts camelCase JS keys to snake_case centrally so every caller can stay idiomatic TS.
- **CSV export is fetch+Blob, not `<a href>`**: the export endpoint requires the same JWT as everything else; a plain browser navigation has no way to attach an `Authorization` header.
