# NFR Design Patterns — Unit 1: Database

## Pattern: Auto-Migrate on Startup with Advisory-Lock Safety

**Category**: Logical Components (resolves Question 1 = A)

**Pattern**: Both Unit 2 (API Service) and Unit 3 (Ingestion Worker Service) run `alembic upgrade head` as the first step of their container entrypoint, before serving requests or polling for jobs. To make this safe when both containers start concurrently (a real possibility under `docker-compose up`), the migration step is wrapped in a **PostgreSQL advisory lock**:

1. Container starts, entrypoint script acquires a session-level advisory lock (a fixed, well-known lock ID reserved for schema migrations) before invoking Alembic
2. If another container already holds the lock (it's mid-migration), the second container blocks until the lock is released
3. Once the lock is acquired, `alembic upgrade head` runs; Alembic's own `alembic_version` table tracking means a container that wakes up second and finds the schema already current is a safe no-op
4. Lock is released, container proceeds to normal startup

**Why this pattern**: Avoids the two most common auto-migrate failure modes — two processes racing to apply the same migration (corrupting `alembic_version`), and a service starting against a not-yet-migrated schema. Standard, low-risk technique; does not require introducing new infrastructure (uses Postgres's built-in advisory locking, no extra lock service needed).

## Pattern: Fail-Fast on Migration Error

**Category**: Resilience (minimal, but worth stating explicitly)

**Pattern**: If `alembic upgrade head` fails (e.g., a migration script error), the container MUST exit non-zero and not proceed to serve requests / poll for jobs against a potentially half-migrated schema. `docker-compose`'s restart policy (decided in Infrastructure Design) then determines retry behavior, but the container itself never silently continues in a bad state.

## N/A Categories (justified)

- **Resilience Patterns** (beyond fail-fast above): No further patterns needed — no runtime service in this unit to retry/circuit-break
- **Scalability Patterns**: N/A — single PostgreSQL instance sufficient per NFR Requirements assessment
- **Performance Patterns**: Already fully addressed via the indexing strategy in `nfr-requirements.md`; no caching layer or read replica warranted at this data volume
- **Security Patterns**: Already fully addressed via NFR-4.1 env-var credential handling; no additional pattern (encryption-at-rest, row-level security, etc.) was raised as a requirement
