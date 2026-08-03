# NFR Requirements Plan — Unit 1: Database

**Input**: `aidlc-docs/construction/database/functional-design/` (approved — 8 entities, 13 business rules, 4 state machines)

## NFR Category Assessment

| Category | Assessment |
|---|---|
| Scalability | **N/A / minimal** — single personal user, low transaction volume (hundreds to low-thousands of rows/year of bank statements). No question needed; documented directly in nfr-requirements.md. |
| Performance | **N/A / minimal** — same rationale; dashboard queries over a small personal dataset need no special tuning beyond sensible indexes, which are decided directly (not a user decision). |
| Availability | **N/A** — personal local deployment, no uptime SLA (requirements.md explicitly opted out of the Resiliency Baseline extension). |
| Security | Baseline secret hygiene still applies (NFR-4.1, not opted out) — DB credentials via environment variables, decided directly, no question needed. |
| Tech Stack Selection | **Real decision** — DB engine and migration-tooling approach need your input (questions below). |
| Reliability | Partial-failure isolation (NFR-2.2) already captured in Unit 1's business-logic-model.md state machines; no further Database-unit-specific question. |
| Maintainability | PBT framework selection (PBT-09) is deferred to Unit 3 (Ingestion Worker Service), where the actual PBT-applicable pure functions (parsing, similarity matching) live — Unit 1 has no pure business-logic functions of its own to test this way (it's schema/migrations only). |
| Usability | N/A — no UI in this unit. |

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (DB engine, migration tooling approach) — PostgreSQL, Alembic/ORM-native
- [x] Step 2: Generate `nfr-requirements.md` — documenting the N/A assessments above plus the resolved tech decisions
- [x] Step 3: Generate `tech-stack-decisions.md` — DB engine + version, migration tool

## Clarifying Questions

### Question 1 — Database Engine
Two separate services (API Service, Ingestion Worker Service) need concurrent read/write access to the same database. Which engine should be used?

A) **PostgreSQL** — client-server relational database, handles concurrent multi-process access well, strong support for the decimal/enum/constraint types this schema needs (BR-1 through BR-13). Requires its own container in docker-compose.

B) **SQLite** — file-based, zero-separate-container simplicity, fine for a single user, but has single-writer-at-a-time locking that could cause contention between the two services during an active ingestion run while the API Service is also being used.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 2 — Migration Tooling Approach
Unit 1 is schema/migrations only, with no language of its own. How should migrations be authored and applied by the two backend units?

A) **Plain, language-agnostic versioned SQL files** owned by Unit 1 (`database/migrations/0001_init.sql`, etc.); each backend unit (API Service, Ingestion Worker Service) applies them at its own startup using a lightweight migration runner in its own language/framework, pointed at the same files. Keeps Unit 1 fully decoupled from whatever language Units 2/3 end up using.

B) **ORM-native migrations** tied to whatever framework the API Service (Unit 2) ends up using (e.g., Alembic if Python, Prisma/TypeORM if Node) — the Ingestion Worker Service applies the same migrations by depending on that same framework/tooling, coupling its tech choice to Unit 2's.

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
