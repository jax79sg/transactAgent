# Unit of Work Dependencies — Bank Transaction Insights App

## Dependency Matrix

| Unit | Depends On | Nature of Dependency |
|---|---|---|
| Unit 1: Database | (none) | Foundational — no other unit's schema/data to depend on |
| Unit 2: API Service | Unit 1 (Database) | Applies migrations at startup; all reads/writes go through this schema |
| Unit 3: Ingestion Worker Service | Unit 1 (Database) | Applies migrations at startup (idempotently, same migration set as Unit 2); reads/writes the same schema, including polling the `ingestion_runs`/jobs table that Unit 2 writes to |
| Unit 4: Frontend SPA | Unit 2 (API Service) | Consumes the REST API exclusively; has no dependency on Unit 1 or Unit 3 directly |

**Note on Unit 2 <-> Unit 3**: They do not depend on each other directly (no direct API calls between them, per Application Design's `services.md`) — they coordinate only indirectly through Unit 1's shared schema (the `ingestion_runs`/jobs table acts as the coordination point). This is intentionally listed as a Unit 1 dependency for both, not a Unit 2 <-> Unit 3 dependency.

## Dependency Diagram

```
          +-------------------------------+
          | Frontend SPA (Unit 4)         |
          +-------------------------------+
                          |
                          | depends on
                          v
          +-------------------------------+
          | API Service (Unit 2)          |
          +-------------------------------+
                          |
                          | depends on
                          v
          +-------------------------------+
          | Database (Unit 1)             |
          +-------------------------------+
                          ^
                          | depends on
                          |
          +-------------------------------+
          | Ingestion Worker Svc (Unit 3) |
          +-------------------------------+
```

**Text validation**: ASCII-only (`+ - | v ^`), no unicode box-drawing; all 4 boxes programmatically verified at exactly 33 characters wide per line.

## Implications for Build Order

Per plan Question 4 (no strong preference, Answer B), Code Generation planning has latitude, but the dependency graph above naturally suggests: **Unit 1 (Database) first**, since both Unit 2 and Unit 3 depend on it; **Unit 2 and Unit 3 can then proceed in either order or in parallel** (they don't depend on each other); **Unit 4 (Frontend) last**, or in parallel with Units 2/3 once API contracts are stable, since it only depends on Unit 2's API surface (which is already fully specified in `component-methods.md`).

## Parallelization Opportunities

- Unit 2 (API Service) and Unit 3 (Ingestion Worker Service) have no direct dependency on each other and can be developed/built in parallel once Unit 1 exists
- Unit 4 (Frontend) can begin against a mocked/contract-defined API surface in parallel with Unit 2, since `component-methods.md` already specifies the API Service's method signatures
