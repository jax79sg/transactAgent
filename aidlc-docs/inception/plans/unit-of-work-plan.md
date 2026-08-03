# Unit of Work Plan — Bank Transaction Insights App

**Input**: `aidlc-docs/inception/application-design/` (approved — 2 services + Frontend SPA, sharing 1 database)

## Proposed Unit Boundaries

Application Design already established 3 independently-deployable pieces. The natural unit-of-work mapping is 1 unit per deployable, plus a decision on who owns the shared schema:

1. **Unit: API Service** — Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration components
2. **Unit: Ingestion Worker Service** — Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion components
3. **Unit: Frontend SPA** — the web UI

## Execution Checklist

- [ ] Step 1: Confirm unit boundaries (3 units as proposed, or adjust) — question below
- [ ] Step 2: Confirm shared-database schema ownership across the 2 backend units — question below
- [ ] Step 3: Confirm code organization / repo structure (greenfield) — question below
- [ ] Step 4: Confirm build/implementation order preference — question below
- [x] Step 5: Generate `unit-of-work.md` — unit definitions, responsibilities, and code organization strategy
- [x] Step 6: Generate `unit-of-work-dependency.md` — dependency matrix between units
- [x] Step 7: Generate `unit-of-work-story-map.md` — mapping of all 24 stories to units
- [x] Step 8: Validate every story is assigned to exactly one primary unit (cross-cutting stories noted explicitly) — complete, 5 stories explicitly flagged as cross-cutting by design

## Clarifying Questions

### Question 1 — Unit Boundaries
Do the 3 proposed units (API Service, Ingestion Worker Service, Frontend SPA) match how you want the work organized, or should they be split/merged differently?

A) Yes, use the 3 units as proposed — matches the approved Application Design's service boundaries exactly

B) Different grouping — describe below

X) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 2 — Shared Database Schema Ownership
The API Service and Ingestion Worker Service share one database but are separately deployable. Something needs to own the schema/migrations so both stay in sync. How should this be organized?

A) A small **shared "Database" unit** (schema + migration scripts only, no runtime logic) that both the API Service and Ingestion Worker Service units depend on and apply at their startup — keeps schema ownership explicit and out of either service's exclusive control

B) The **API Service unit owns migrations**; the Ingestion Worker Service unit only ever reads/writes using that schema without ever running migrations itself — simpler, one clear owner, but the Worker Service now technically depends on API Service's migration code at deploy time

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3 — Code Organization / Repository Structure
This is a fresh (greenfield) codebase with no existing repo structure. How should the units be organized on disk / in version control?

A) **Monorepo** — single git repository at the workspace root, with top-level directories per unit (e.g., `api-service/`, `ingestion-worker/`, `frontend/`, `database/`) plus the top-level `docker-compose.yml` — simplest for a single-developer/AI-driven personal project

B) **Multiple repos** — one git repository per unit, referenced/composed together only via docker-compose — more separation, more overhead to keep in sync

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 4 — Implementation/Build Order
Should the units be implemented in a specific sequence, or does it matter?

A) **Database/schema first, then API Service, then Ingestion Worker Service, then Frontend last** — bottom-up, each unit can be built/tested against real dependencies as they become available

B) **No strong preference** — let the AI decide the most sensible order during Code Generation planning

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
