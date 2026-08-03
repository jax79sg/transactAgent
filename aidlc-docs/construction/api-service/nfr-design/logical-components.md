# Logical Components — Unit 2: API Service

## Component: FastAPI Application
- **Type**: ASGI web application (single process, run under Uvicorn)
- **Role**: Hosts all 5 business components' routes (Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration)

## Component: JWT Auth Dependency
- **Type**: FastAPI dependency (in-process, no external service)
- **Role**: Validates `Authorization` header on every protected route; see `nfr-design-patterns.md`

## Component: DB Session Dependency
- **Type**: FastAPI dependency wrapping a SQLAlchemy `Session`
- **Role**: Per-request session lifecycle, using the shared `transactagent_db` models from Unit 1

## Component: CORS Middleware
- **Type**: FastAPI/Starlette built-in middleware
- **Role**: Restricts browser-based cross-origin requests to the configured Frontend origin

## No Additional Infrastructure Components

No cache, queue, or circuit-breaker component is introduced — consistent with the "keep it simple" decision from Application Design. The only cross-service coordination this unit performs (writing `IngestionRun`/`RecategorizationJob` rows for Unit 3 to pick up) is plain database writes via the DB Session Dependency above, not a separate messaging component.
