# Code Generation Plan — Unit 2: API Service

**Workspace root**: `/Volumes/1TB/projects/transactAgent`
**Code location for this unit**: `api-service/` directory at workspace root

## Unit Context

- **Stories implemented**: US-1.2 (trigger/status half), US-1.5, US-3.1–3.7, US-4.1–4.6, US-5.1, US-5.2, US-5.3 (env config half)
- **Dependencies**: Unit 1 (`database` package — installed as local editable dependency for models + migration helper)
- **Dependents**: Unit 4 (Frontend) calls this unit's REST API
- **Interfaces**: REST API per `functional-design/domain-entities.md` DTOs
- **Database entities owned**: None (reuses Unit 1's schema)

## Steps

- [x] Step 1: Project Structure Setup — created `api-service/pyproject.toml`, `src/api_service/{__init__.py, config.py, db.py, errors.py}` (10 typed exceptions covering AR-1..AR-9)
- [x] Step 2: Business Logic Generation — created `auth/security.py` + `auth/dependencies.py`, `transactions/{schemas,service}.py`, `dashboards/{schemas,service}.py`, `ingestion/{schemas,service}.py`, `categories/{schemas,service}.py` (repository-layer calls forward-reference Step 5, written next)
- [x] Step 3: Business Logic Unit Testing — created `tests/conftest.py` (testcontainers Postgres fixture, reused pattern) and `tests/{test_auth_security, test_categories_service, test_transactions_service, test_ingestion_service, test_dashboards_service}.py` covering AR-2/3/4/5/6/7/9/10 with positive and negative cases
- [x] Step 4: Business Logic Summary — created `aidlc-docs/construction/api-service/code/business-logic-summary.md`
- [x] Step 5: Repository Layer Generation — created `categories/repository.py`, `transactions/repository.py` (filter/sort/group query builders — a pure function, PBT candidate once framework is chosen), `dashboards/repository.py`, `ingestion/repository.py`. **Note**: executed before Step 3 in practice (tests need the repository layer to exist to run against), plan order preserved for documentation purposes.
- [x] Step 6: Repository Layer Unit Testing — covered by Step 3's service-layer tests (which exercise the repository layer transitively via testcontainers Postgres); no separate repository-only test file needed since these are thin pass-through query wrappers with no independent branching logic
- [x] Step 7: Repository Layer Summary — folded into Step 4's summary document above
- [x] Step 8: Frontend Components Generation — **N/A**, this unit has no UI (Frontend is Unit 4)
- [x] Step 9: API Layer Generation — created `auth/{schemas,repository,router}.py`, `transactions/router.py`, `dashboards/router.py`, `ingestion/router.py`, `categories/router.py`, `health.py`, `main.py` (CORS, exception handlers, lifespan-based startup migration, all routers registered)
- [x] Step 10: API Layer Unit Testing — created `tests/test_api_{health,auth,categories,transactions,ingestion,dashboards}.py` using FastAPI's `TestClient`. **Actually executed** (installed both packages into a real venv, ran against a real dockerized Postgres via testcontainers) rather than relying on syntax checks alone — found and fixed 3 real bugs in the process (see audit.md). Final result: 41/41 passing.
- [x] Step 11: API Layer Summary — created `aidlc-docs/construction/api-service/code/api-layer-summary.md`
- [x] Step 12: Database Migration Scripts — **N/A**, Unit 1 owns all migrations; this unit only calls `run_migrations_with_lock()` at startup (already covered in Step 9's `main.py`)
- [x] Step 13: Documentation Generation — created `aidlc-docs/construction/api-service/code/README.md`
- [x] Step 14: Deployment Artifacts Generation — created `api-service/Dockerfile` (build context corrected to workspace root so it can `COPY` the sibling `database/` package — also fixed the same bug in `infrastructure-design.md`'s draft), added the `api-service` entry to root `docker-compose.yml`, updated `.env.example` with `JWT_SECRET`/`FRONTEND_ORIGIN`. Validated with `docker compose config` (parses cleanly).

## Story Traceability
US-1.2, US-1.5, US-3.1–3.7, US-4.1–4.6, US-5.1, US-5.2, US-5.3 — all covered by the components generated in Steps 2, 5, 9 per `unit-of-work-story-map.md`.

---

This plan is the single source of truth for Unit 2 Code Generation.
