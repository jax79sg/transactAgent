# Infrastructure Design Plan — Unit 1: Database

**Input**: `aidlc-docs/construction/database/nfr-design/` (approved), `aidlc-docs/inception/requirements/requirements.md` (NFR-1.1 full containerization, NFR-1.2 externalized config)

## Infrastructure Category Assessment

| Category | Assessment |
|---|---|
| Deployment Environment | Already fixed: local docker-compose (NFR-1.1) — no question needed |
| Compute Infrastructure | N/A — this unit has no compute of its own (it's the DB engine + migration scripts, not a service) |
| Storage Infrastructure | **Real decision**: volume persistence approach — question below |
| Messaging Infrastructure | N/A — no message broker (per NFR Design decision, coordination is plain DB rows) |
| Networking Infrastructure | **Real decision**: whether to expose the DB port to the host — question below |
| Monitoring Infrastructure | N/A — no monitoring/alerting stack in scope (Resiliency Baseline extension opted out) |
| Shared Infrastructure | Real decision folded into readiness/ordering question below — this container is depended upon by Units 2 and 3 |

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (volume persistence, port exposure, startup ordering/healthcheck) — bind mount, internal-only, healthcheck+depends_on
- [x] Step 2: Generate `infrastructure-design.md` — the `database` docker-compose service definition
- [x] Step 3: Generate `deployment-architecture.md` — how this fits the overall docker-compose topology (referencing Units 2/3/4 as consumers, to be finalized once those units' Infrastructure Design stages run)

## Clarifying Questions

### Question 1 — Volume Persistence
Per NFR-2.1 (data must survive container restarts), how should the PostgreSQL data directory be persisted?

A) **Named Docker volume** (e.g., `pgdata:`) — managed by Docker, survives `docker-compose down` (but not `docker-compose down -v`), simplest and most portable option, doesn't clutter the project directory

B) **Bind mount to a host directory** (e.g., `./data/postgres:/var/lib/postgresql/data`) — data lives in a visible project-relative folder, easy to back up/inspect directly from the host filesystem, but has file-permission quirks that can vary by host OS

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 2 — Port Exposure
Should the PostgreSQL port (5432) be exposed to your host machine (e.g., for connecting with a DB GUI tool like pgAdmin/TablePlus), or kept internal to the docker-compose network only?

A) **Expose to host** (`ports: ["5432:5432"]`) — lets you connect directly from your machine with any Postgres client for debugging/inspection

B) **Internal-only** (no `ports:` mapping, only accessible to other containers on the compose network) — slightly more contained, but you'd need to `docker exec` in or temporarily add a port mapping to inspect the DB directly

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 3 — Startup Ordering / Readiness
Units 2 and 3 both depend on this database being ready (and migrated) before they start serving/polling. How should docker-compose enforce this?

A) **Healthcheck + `depends_on: condition: service_healthy`** — the `database` service defines a `pg_isready`-based healthcheck; Units 2/3's compose entries wait for it to report healthy before their own containers start (their own containers still run the advisory-lock-guarded migration themselves per NFR Design, but at least they don't start against a DB that isn't even accepting connections yet)

B) **No explicit ordering** — rely on each service's own retry/reconnect logic to handle the database not being ready yet at first boot

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
