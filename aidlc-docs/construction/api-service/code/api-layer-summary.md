# API Layer Summary — Unit 2: API Service

FastAPI application in `api-service/src/api_service/main.py`, routers per domain area. All routes except `/auth/login` and `/health` require a valid JWT (AR-1), enforced via `Depends(get_current_user_id)` at the router level.

| Router | Base path | Endpoints |
|---|---|---|
| `health.py` | `/health` | `GET /health` (unauthenticated) |
| `auth/router.py` | `/auth` | `POST /auth/login` |
| `transactions/router.py` | `/transactions` | `GET /transactions`, `GET /transactions/export.csv`, `PUT /transactions/{id}/category` |
| `dashboards/router.py` | `/dashboards` | `GET /dashboards/category-trends`, `GET /dashboards/cash-flow`, `GET /dashboards/bank-breakdown` |
| `ingestion/router.py` | `/ingestion` | `POST /ingestion/runs`, `GET /ingestion/runs`, `GET /ingestion/runs/{id}`, `GET /ingestion/runs/{id}/files` |
| `categories/router.py` | `/categories` | `GET /categories`, `POST /categories`, `PUT /categories/{id}`, `DELETE /categories/{id}` |
| `drive_connect/router.py` | `/drive` | `GET /drive/connect` (auth), `GET /drive/callback` (unauthenticated — hit by Google's redirect, CSRF-protected via `state`), `GET /drive/status` (auth). Added 2026-08-01 retroactively — see audit.md. |
| `recategorization/router.py` | `/recategorization` | `GET /recategorization/proposals`, `GET /recategorization/proposals/pending-count`, `POST /recategorization/proposals/{id}/approve`, `POST /recategorization/proposals/{id}/reject`, `POST /recategorization/proposals/bulk-approve`, `POST /recategorization/proposals/bulk-reject`. Added 2026-08-02 (Epic 6). |

**Conventions**:
- JSON request/response bodies use camelCase (via the shared `CamelModel` base in `schemas.py`), matching `functional-design/domain-entities.md`. Query-parameter-bound filter models (`TransactionFilter`, `TransactionListQuery`, `DashboardFilter`) intentionally stay snake_case — a deliberate choice to avoid FastAPI/Pydantic's alias-generator interacting unpredictably with `Depends()`-bound query parameters.
- All business-rule violations (AR-1 through AR-10) raise a typed `ApiError` subclass, mapped by a single global exception handler to a consistent `{error, message, details}` JSON shape with the correct HTTP status code.
- Startup runs `run_migrations_with_lock()` (Unit 1's advisory-lock pattern) via FastAPI's `lifespan` context, skippable via `create_app(run_migrations=False)` for tests.
- Interactive docs available at `/docs` and `/redoc` (NFR Requirements Question 2 = A).
