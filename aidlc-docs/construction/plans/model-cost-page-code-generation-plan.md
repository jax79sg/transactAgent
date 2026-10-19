# Code Generation Plan — Model Cost Page (issue #28, 2026-10-07)

**Requirements**: `inception/requirements/model-cost-page-requirements.md`. **Units**: Database, Ingestion Worker, API Service, Frontend, deployment files. **Branch**: `feature/issue-28-model-cost-page`.

## Steps
1. [x] **Database** — `ModelUsage` model (`model_usage`), migration 0021, `transactagent_db/model_usage.py` (cost arithmetic, token estimate, `record_model_usage`), tests.
2. [x] **Settings** — three price settings in both services' `config.py`, the API catalog (category "Model Costs"), `docker-compose.yml`, `.env.example`; catalog-count assertions.
3. [x] **Worker recording** — extraction, categorisation (both calls) and embedding clients; tests that a call records, a failed call does not, a local call does not, a recording failure does not break the call.
4. [x] **API recording** — Ask AI client; same tests.
5. [x] **API endpoint** — `GET /costs` (repository, service, schemas, router), time-zone-aware grouping; tests against a real database.
6. [x] **Frontend** — `api/costs.ts`, types, `CostsPage` (summary, chart, period table, group table), route, nav link; tests.
7. [x] **Verification** — suites, `ruff`, `tsc`, `eslint`; scratch-copy mutation checks on the arithmetic, the grouping and the recording paths; migration up and down on a scratch database; the page seen in the browser against the real stack.
8. [x] **Documentation and progress** — requirements, this plan, summary, `aidlc-state.md`, `audit.md`.

## Completion criteria
All steps `[x]`; suites pass; a real Gemini call leaves a row that the page shows. **Met** against a scratch stack (the live stack was deliberately not touched: deploying is the user's call, see the summary).
