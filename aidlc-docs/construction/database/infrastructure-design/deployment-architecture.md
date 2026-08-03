# Deployment Architecture — Unit 1: Database (in context of overall system)

## Overall Topology

**Corrected 2026-08-01** (during Unit 2's Infrastructure Design): the original version of this diagram (drafted during Unit 1's Infrastructure Design, before Units 2/3 details existed) incorrectly showed `ingestion-worker` depending on `api-service`. Per the approved `unit-of-work-dependency.md`, Units 2 and 3 do **not** depend on each other — both depend independently on `database` (Unit 1) only, coordinating solely through shared table rows. The diagram below reflects the correct topology.

**Text validation**: ASCII-only (`+ - | v ^`), no unicode box-drawing; all 4 boxes programmatically verified at exactly 33 characters wide per line.

```
          +-------------------------------+
          | Frontend SPA (Unit 4) :8787   |
          +-------------------------------+
                          |
                          | depends on (REST)
                          v
          +-------------------------------+
          | api-service (Unit 2) :7878    |
          +-------------------------------+
                          |
                          | depends_on: healthy
                          v
          +-------------------------------+
          | database (Unit 1)             |
          +-------------------------------+
                          ^
                          | depends_on: healthy
                          |
          +-------------------------------+
          | ingestion-worker (Unit 3)     |
          +-------------------------------+
```

**Status**: All 4 units finalized (`database`, `api-service` :7878, `ingestion-worker`, `frontend` :8787). The full topology is present in the real root `docker-compose.yml` once Unit 4's Code Generation completes — at that point the whole stack is startable via a single `docker-compose up` (NFR-1.1).

## Shared Infrastructure Notes

- All services share one Docker network (`transactagent-net`, bridge driver, default docker-compose behavior) — no custom networking required for a single-host personal deployment.
- `database` is the only stateful service with a bind-mounted volume; Units 2/3/4 are expected to be stateless containers (any state they need lives in this database).
- This document, along with Units 2/3/4's equivalents, feeds directly into the root `docker-compose.yml` produced during Code Generation (NFR-1.1 — the whole stack must start via a single `docker-compose up`).
