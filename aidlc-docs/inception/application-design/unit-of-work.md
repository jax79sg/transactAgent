# Units of Work — Bank Transaction Insights App

Per plan decisions: 3 proposed units (Question 1 = A) plus a dedicated shared Database unit (Question 2 = A) = **4 units total**. Code organization: monorepo (Question 3 = A). Build order: no fixed preference — determined during Code Generation planning (Question 4 = B), though a database-first, then-backend, then-frontend sequence is the natural dependency order and will likely be followed.

**Addendum (2026-08-17, Categorization Model Fine-Tuning feature)**: A 5th unit is added — **Model Training** (see below) — the first addition to this list since the original 4. Unlike Units 2-4, it is deliberately not a docker-compose service.

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

## Unit 5: Model Training *(added 2026-08-17, Categorization Model Fine-Tuning feature — see `categorization-model-finetuning-application-design-plan.md`)*

- **Type**: Standalone offline tooling — **not** a docker-compose service, no runtime process, no container. Two manual CLI entry points, run on demand.
- **Responsibilities**: Curate a fine-tuning dataset from labeled transactions (FR-CFT-1..4); fine-tune the categorization model via mlx-tune, evaluate it, and save the resulting artifact (FR-CFT-5..8).
- **Owns components from Application Design**: Dataset Curator, Fine-Tuning Trainer
- **Depends on**: Unit 1 (Database schema — read-only; the first unit with a read-only relationship to Unit 1, every other unit above both reads and writes)
- **Code organization**: `model-training/` directory at repo root, alongside the 4 existing unit directories — but deliberately **excluded** from `docker-compose.yml` (no service entry) and given its own isolated Python dependency manifest, per NFR-CFT-1, since mlx-tune/ClearML are heavyweight ML dependencies not needed by (and not to be added to) any of the other 4 units' environments.

---

## Code Organization Strategy (Greenfield, Monorepo)

```
transactAgent/                  (workspace root — application code, NEVER in aidlc-docs/)
  database/                     (Unit 1)
  api-service/                  (Unit 2)
  ingestion-worker/             (Unit 3)
  frontend/                     (Unit 4)
  model-training/               (Unit 5 — added 2026-08-17, no docker-compose entry)
  docker-compose.yml            (orchestrates Units 1-4's containers; Unit 5 is deliberately absent)
  .env.example                  (documents required secrets/config, no real values)
  aidlc-docs/                   (documentation only — unchanged)
```

Single git repository at the workspace root (Question 3 = A). Each unit directory is self-contained with its own dependency manifest (e.g., `requirements.txt`/`pyproject.toml` or `package.json`, exact choice made in NFR Requirements per unit) and its own `Dockerfile`. **Exception**: Unit 5 has a dependency manifest (its own `pyproject.toml`/`requirements.txt`, exact tooling decided at NFR Requirements) but no `Dockerfile`/container — it runs directly on the host per Resolved Decision 9 (`categorization-model-finetuning-requirements.md`).
