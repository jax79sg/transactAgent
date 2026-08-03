# Code Generation Plan — Unit 1: Database

**Workspace root**: `/Volumes/1TB/projects/transactAgent` (from `aidlc-state.md`)
**Project type**: Greenfield, multi-unit monorepo (per `unit-of-work.md` Question 3 = A)
**Code location for this unit**: `database/` directory at workspace root (per `unit-of-work.md`)

## Unit Context

- **Stories implemented**: None directly user-facing (Unit 1 has no assigned "primary" stories per `unit-of-work-story-map.md` — it's the foundational schema every other unit's stories depend on)
- **Dependencies**: None (foundational unit)
- **Dependents**: Unit 2 (API Service), Unit 3 (Ingestion Worker Service) — both install this as a local editable Python package and apply its Alembic migrations
- **Database entities owned**: All 8 (User, Category, BankStatement, Transaction, FxRateCache, IngestionRun, IngestionRunFile, RecategorizationJob) — per `functional-design/domain-entities.md`
- **PBT applicability**: N/A for this unit — no pure business-logic/transformation functions exist here (declarative schema + constraints only); PBT framework selection was already deferred to Unit 3 in NFR Requirements. Example-based tests are used instead to verify constraints.

## Steps

- [x] Step 1: Project Structure Setup — created `database/pyproject.toml`, `database/src/transactagent_db/__init__.py`, `database/alembic.ini`, `database/migrations/env.py`, `database/migrations/script.py.mako`, `database/migrations/versions/`, `database/tests/`
- [x] Step 2: Domain Models Generation — created `database/src/transactagent_db/models.py`: SQLAlchemy 2.0-style models for all 8 entities, with CHECK/UNIQUE constraints and indexes implementing BR-1 through BR-13 (BR-5, BR-6, BR-11, BR-12 documented as application-layer rules where a standing SQL constraint isn't expressible; BR-10 deferred to raw SQL in the initial migration)
- [x] Step 3: Domain Models Unit Testing — created `database/tests/conftest.py` (testcontainers-backed Postgres fixture, per-test rollback isolation) and `database/tests/test_models.py` (9 tests covering BR-2, BR-3, BR-4, BR-7, BR-9, including negative cases)
- [x] Step 4: Domain Models Summary — created `aidlc-docs/construction/database/code/models-summary.md`
- [x] Step 5: Database Migration Scripts — created `database/migrations/versions/0001_initial_schema.py`; creates the full schema from `Base.metadata` (single source of truth in models.py) plus the BR-10 partial-unique-index as raw SQL
- [x] Step 6: Category Whitelist Seed Script — created `database/src/transactagent_db/seed_categories.py` (idempotent — matches by name, only inserts missing rows) with all 45 user-supplied categories plus reserved `UNSURE`
- [x] Step 7: Advisory-Lock Migration Helper — created `database/src/transactagent_db/migrate.py`: `build_database_url()` (also reused by `migrations/env.py`, removing duplication) and `run_migrations_with_lock()` implementing the NFR Design advisory-lock + fail-fast pattern
- [x] Step 8: Documentation Generation — created `aidlc-docs/construction/database/code/README.md`
- [x] Step 9: Deployment Artifacts Generation — created root `docker-compose.yml` (`database` service per `infrastructure-design.md`), `.env.example`, and `.gitignore` (excludes `.env`, the bind-mounted `data/` directory, and Python build artifacts)

## Story Traceability
No stories are directly implemented by this unit (see Unit Context above); this plan instead traces to Unit 1's own functional/NFR/infrastructure design artifacts (`domain-entities.md`, `business-rules.md`, `business-logic-model.md`, `nfr-requirements.md`, `nfr-design-patterns.md`, `infrastructure-design.md`), which in turn trace to FR-2 through FR-10 and NFR-2 as documented in those files.

---

This plan is the single source of truth for Unit 1 Code Generation. Each step will be executed in order and marked `[x]` immediately on completion.
