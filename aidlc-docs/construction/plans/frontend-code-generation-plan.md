# Code Generation Plan — Unit 4: Frontend SPA

**Workspace root**: `/Volumes/1TB/projects/transactAgent`
**Code location**: `frontend/` directory at workspace root

## Unit Context

- **Stories implemented**: All 24 (Frontend is the UI for every story)
- **Dependencies**: Unit 2's REST API only (no dependency on Unit 1's `database` package)
- **Interfaces consumed**: `api-service/functional-design/domain-entities.md` DTOs, `api-service/code/api-layer-summary.md` endpoint list

## Steps

- [x] Step 1: Project Structure Setup — created `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, Tailwind/PostCSS config, `src/index.css`, `src/config.ts` (`main.tsx`/`App.tsx` deferred to Step 4 once routing/auth exist to wire up)
- [x] Step 2: API Client Layer — created `src/api/{client,types,auth,transactions,dashboards,ingestion,categories,driveConnect}.ts`. **Bugs caught before running anything**: (1) Unit 2's query params are snake_case (plain BaseModel/FastAPI Query, e.g. `date_from`) unlike its camelCase JSON bodies — every filter would have silently been ignored; fixed with a centralized camelCase->snake_case conversion in `client.ts`'s `buildUrl()`. (2) The CSV export endpoint requires the same JWT as every other route, so it can't be a plain `<a href>` navigation (no way to attach an Authorization header) — implemented as fetch+Blob+programmatic-anchor instead; updated `frontend-components.md` to record the resolution.
- [x] Step 3: Pure Logic + PBT Testing — created `src/lib/urlFilterState.ts` and `tests/{setup,urlFilterState.test}.ts` (fast-check: round-trip losslessness, idempotency, empty-state, invalid-enum-dropped)
- [x] Step 4: Auth & Routing Infrastructure — created `src/context/AuthContext.tsx` (sessionStorage per Question 1 = C, centralized 401 handling), `src/components/{ProtectedLayout,ErrorBoundary,NavBar}.tsx`, `src/{main,App}.tsx` (router + QueryClientProvider). Pages referenced by `App.tsx` are created next (Steps 5-9).
- [x] Step 5: LoginPage — form, validation, error handling
- [x] Step 6: DashboardPage — 3 tabs (Radix Tabs), date range filter, Chart.js charts (Bar for category-trends/bank-breakdown, Line for cash-flow), disclosure banners, click-to-drill-down navigation to `/transactions`
- [x] Step 7: TransactionsPage — URL-driven filter state (via `urlFilterState.ts`), table with grouping selector, Radix Select inline category correction, UNSURE quick-filter toggle, blob-based CSV export, pagination
- [x] Step 8: IngestionPage — trigger button (409-recovery via `startRun`'s existing-run fallback), 3s active-run polling via TanStack Query `refetchInterval`, run history with click-to-expand file drilldown, page-reload recovery of an in-progress run
- [x] Step 9: SettingsPage — category CRUD (Radix Dialog delete-confirmation, blocked-count error display), Drive connection card (`?driveConnected=true` callback handling, invalidates status query on return)
- [x] Step 10: Component/Logic Unit Testing — created `tests/{apiClient,LoginPage}.test.tsx`. **Actually executed**: `npm install`, `npm run build` (tsc + vite), `npm test` (vitest). Found and fixed 3 real bugs before ever running against a live backend: (1) Unit 2's query params are snake_case not camelCase (see Step 2); (2) `Record<string, unknown>` structural-typing mismatch for filter-state objects passed as query params; (3) `global.fetch` unavailable under `tsc -b`'s Node-less lib config (worked under Vitest's runtime but failed the stricter build type-check) — switched to `globalThis.fetch`. Final: 12/12 tests passing, clean production build.
- [x] Step 11: Documentation Generation — created `aidlc-docs/construction/frontend/code/README.md`
- [x] Step 12: Deployment Artifacts Generation — created `frontend/{Dockerfile,nginx.conf,docker-entrypoint.sh}`, added `frontend` service to root `docker-compose.yml`, updated `.env.example` (`API_BASE_URL` + `FRONTEND_ORIGIN` synced to `:8787`). **2 more real bugs caught before running anything**: (1) `nginx:alpine` has no `curl` — the healthcheck as first drafted (in Infrastructure Design) would have always failed; switched to `wget --spider` (Alpine busybox default). (2) `COPY frontend/ ./` after `npm ci` in the Dockerfile would have overwritten the container's Linux `node_modules` with the locally-installed macOS one (native binary mismatch, e.g. esbuild) since a local `node_modules` already existed on disk from Step 1's `npm install` — added a root `.dockerignore` excluding `node_modules/` from the whole build context. Validated `docker-compose.yml` with `docker compose config`.

## Story Traceability
All 24 stories — covered across Steps 5-9 (one page per epic-ish grouping, per `unit-of-work-story-map.md`).

---

This plan is the single source of truth for Unit 4 Code Generation — the final unit.
