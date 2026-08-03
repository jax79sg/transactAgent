# NFR Design Plan — Unit 1: Database

**Input**: `aidlc-docs/construction/database/nfr-requirements/` (approved — PostgreSQL, Alembic/SQLAlchemy, Python 3.12+)

## NFR Design Category Assessment

| Category | Assessment |
|---|---|
| Resilience Patterns | **N/A** — no runtime service to apply retry/circuit-breaker patterns to; the only resilience-relevant behavior (partial-failure isolation) lives in Units 2/3's application logic, already modeled at the state-machine level in Unit 1's functional design |
| Scalability Patterns | **N/A** — no scaling target set in NFR Requirements; a single PostgreSQL instance is sufficient |
| Performance Patterns | Indexing strategy already decided in NFR Requirements (nfr-requirements.md); no additional pattern (e.g., caching layer, read replicas) is warranted at this data volume |
| Security Patterns | Covered by NFR-4.1 (env-var credentials) — no additional pattern needed (no encryption-at-rest requirement was raised, no compliance regime opted into) |
| Logical Components | **Real decision**: how/when migrations are applied — question below |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (migration application pattern) — Answer: A, auto-migrate with advisory-lock safety
- [x] Step 2: Generate `nfr-design-patterns.md`
- [x] Step 3: Generate `logical-components.md`

## Clarifying Question

### Question 1 — Migration Application Pattern
How should Alembic migrations actually get applied to the running PostgreSQL instance?

A) **Auto-migrate on startup** — both Unit 2 (API Service) and Unit 3 (Ingestion Worker Service) run `alembic upgrade head` automatically as part of their container's startup sequence, before accepting traffic/processing jobs. Simplest for a personal docker-compose app — `docker-compose up` always leaves the schema current.

B) **Manual/explicit migration step** — migrations are applied via a separate one-off command you run yourself (e.g., `docker-compose run api-service alembic upgrade head`) before starting the services. More control, but an extra manual step every time the schema changes.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
