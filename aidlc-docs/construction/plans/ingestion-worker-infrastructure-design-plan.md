# Infrastructure Design Plan — Unit 3: Ingestion Worker Service

**Input**: `aidlc-docs/construction/ingestion-worker/nfr-design/` (approved)

## Infrastructure Category Assessment

| Category | Assessment |
|---|---|
| Deployment Environment | Fixed: local docker-compose |
| Compute Infrastructure | Single container running the `asyncio` worker loop as its main process (no web server) |
| Storage Infrastructure | N/A — stateless, all state in `database` (Unit 1) |
| Messaging Infrastructure | N/A — no broker |
| Networking Infrastructure | **No host port needed** — unlike Unit 2, nothing (no browser, no other service) ever calls into Unit 3 directly; it only reaches out to `database` and external APIs |
| Monitoring Infrastructure | **Real decision**: liveness visibility — question below |
| Shared Infrastructure | `depends_on: database (healthy)`, same advisory-lock migration pattern as Units 1/2 |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (liveness/health visibility) — Answer: A, file-based heartbeat
- [x] Step 2: Generate `infrastructure-design.md` — the `ingestion-worker` docker-compose service definition
- [x] Step 3: Update the shared `deployment-architecture.md` with Unit 3's finalized entry

## Clarifying Question

### Question 1 — Liveness/Health Visibility
Nothing else `depends_on` Unit 3 being healthy (unlike Units 1/2), so a Docker healthcheck isn't functionally required for startup ordering. But without one, `docker compose ps` can't tell you if the worker loop has silently died (vs. the container just being up but the Python process crashed and Docker didn't notice). Should a minimal healthcheck be added anyway?

A) **Yes — a tiny file-based heartbeat**: the worker loop touches/updates a timestamp file (or a DB row) on every poll cycle; the Docker healthcheck script checks that file's recency (e.g., updated within the last 30s). No extra HTTP server needed, but gives real operational visibility.

B) **No healthcheck** — rely on `restart: unless-stopped` and manual `docker logs` inspection if something seems wrong; simplest, but a silently-hung worker (not crashed, just stuck) wouldn't be caught automatically either way

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
