# Logical Components — Unit 1: Database

## Component: PostgreSQL Instance
- **Type**: Data store (external to application code, provisioned as a container — exact image/version/volume mapping finalized in Infrastructure Design)
- **Role**: Hosts the schema defined in `functional-design/domain-entities.md`

## Component: Migration Runner (embedded in Unit 2 and Unit 3 entrypoints)
- **Type**: Startup-time logic, not a standalone service
- **Role**: Applies Alembic migrations from the shared `database/` package's migration scripts, guarded by the advisory-lock pattern (`nfr-design-patterns.md`)
- **Note**: This is logic embedded in each backend unit's own container entrypoint, not a component Unit 1 runs itself (Unit 1 remains "schema/migrations only, no runtime service" per `unit-of-work.md`) — Unit 1 supplies the migration scripts and SQLAlchemy models; Units 2/3 supply the entrypoint logic that applies them.

## Component: Shared SQLAlchemy Model Package
- **Type**: Python package (installed as a local/editable dependency by Units 2 and 3, per `tech-stack-decisions.md`)
- **Role**: Single source of truth for the schema — both backend units import from here rather than each maintaining their own model definitions, preventing schema drift between two separately-deployable services

## No Additional Infrastructure Components

No queue, cache, or circuit-breaker component is introduced for this unit — the run/job coordination "queue" pattern (from Application Design `services.md`) is implemented as plain table rows (`IngestionRun`, `RecategorizationJob`) within this same PostgreSQL instance, not a separate message broker, consistent with the "keep the docker-compose stack simple" decision made in Application Design.
