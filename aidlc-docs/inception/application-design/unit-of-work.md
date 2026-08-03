# Units of Work — Bank Transaction Insights App

Per plan decisions: 3 proposed units (Question 1 = A) plus a dedicated shared Database unit (Question 2 = A) = **4 units total**. Code organization: monorepo (Question 3 = A). Build order: no fixed preference — determined during Code Generation planning (Question 4 = B), though a database-first, then-backend, then-frontend sequence is the natural dependency order and will likely be followed.

---

## Unit 1: Database

- **Type**: Shared schema/migration package (no runtime service, no independently running process)
- **Responsibilities**: Own the canonical schema definition and migration scripts for: `users`, `transactions`, `processed_statements`, `categories`, `ingestion_runs`/jobs, `fx_rate_cache`. Both the API Service and Ingestion Worker Service apply these migrations at their own startup against the shared database instance.
- **Owns components from Application Design**: The "Shared Database" data store itself (schema only — no business logic lives here)
- **Code organization**: `database/` directory at repo root — migration scripts + schema definition, packaged so both other units can reference/apply them (e.g., as a versioned migration tool config both services invoke on boot)

## Unit 2: API Service

- **Type**: Independently deployable backend service (container)
- **Responsibilities**: All Frontend-facing REST API concerns — auth, transaction management, dashboards/insights, ingestion trigger & status, configuration
- **Owns components from Application Design**: Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration
- **Depends on**: Unit 1 (Database schema)
- **Code organization**: `api-service/` directory at repo root

## Unit 3: Ingestion Worker Service

- **Type**: Independently deployable backend service (container)
- **Responsibilities**: All asynchronous, external-integration-heavy work — Drive access, statement extraction (OCR + LLM-assisted), categorization, currency conversion, run orchestration
- **Owns components from Application Design**: Ingestion Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion
- **Depends on**: Unit 1 (Database schema — reads/writes the same tables, including polling the ingestion-runs/jobs table written by Unit 2)
- **Code organization**: `ingestion-worker/` directory at repo root

## Unit 4: Frontend SPA

- **Type**: Independently deployable web client (container, served as static assets or via a lightweight dev/prod server)
- **Responsibilities**: The entire rich UI — login, ingestion trigger/progress/history, transaction table (filter/group/sort/export/correction), dashboards with drill-down, category whitelist settings
- **Owns components from Application Design**: Frontend SPA
- **Depends on**: Unit 2 (API Service's REST API — the Frontend never talks to the Database or Ingestion Worker Service directly)
- **Code organization**: `frontend/` directory at repo root

---

## Code Organization Strategy (Greenfield, Monorepo)

```
transactAgent/                  (workspace root — application code, NEVER in aidlc-docs/)
  database/                     (Unit 1)
  api-service/                  (Unit 2)
  ingestion-worker/             (Unit 3)
  frontend/                     (Unit 4)
  docker-compose.yml            (orchestrates all 4 units + the DB engine container)
  .env.example                  (documents required secrets/config, no real values)
  aidlc-docs/                   (documentation only — unchanged)
```

Single git repository at the workspace root (Question 3 = A). Each unit directory is self-contained with its own dependency manifest (e.g., `requirements.txt`/`pyproject.toml` or `package.json`, exact choice made in NFR Requirements per unit) and its own `Dockerfile`.
