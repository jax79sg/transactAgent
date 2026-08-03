# Infrastructure Design Plan — Unit 2: API Service

**Input**: `aidlc-docs/construction/api-service/nfr-design/` (approved)

## Infrastructure Category Assessment

| Category | Assessment |
|---|---|
| Deployment Environment | Fixed: local docker-compose |
| Compute Infrastructure | Single container, Uvicorn running the FastAPI app (single worker process — appropriate for one user; no `--reload`, this is the "real" app, not a dev hot-reload server) — decided directly |
| Storage Infrastructure | N/A — stateless service, all state lives in the `database` service (Unit 1) |
| Messaging Infrastructure | N/A — no broker, per Application Design |
| Networking Infrastructure | **Real decision**: unlike the internal-only `database` service, this API **must** be reachable by the browser directly (the Frontend SPA runs client-side and calls this API via `fetch`, and CORS was just configured for exactly that) — so it needs a host port mapping. Question below is just which port number, since only you know what's already in use on your machine. |
| Monitoring Infrastructure | N/A — no monitoring stack in scope |
| Shared Infrastructure | Depends on `database` (per Unit 1's healthcheck + advisory-lock migration pattern, both reused here); Unit 4 (Frontend) will depend on this service in turn |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (host port number) — Answer: B, port 7878
- [x] Step 2: Generate `infrastructure-design.md` — the `api-service` docker-compose service definition
- [x] Step 3: Update `deployment-architecture.md` (shared, started in Unit 1) with Unit 2's finalized service entry — also corrected an inaccurate Unit2->Unit3 dependency arrow left over from Unit 1's draft

## Clarifying Question

### Question 1 — Host Port
Which host port should the API Service be exposed on (`http://localhost:<port>`)?

A) **8000** (common FastAPI/uvicorn convention)

B) **A different port** — specify after [Answer]: tag below (e.g., if 8000 is already used by something else on your machine)

X) Other (please describe after [Answer]: tag below)

[Answer]:B. 7878

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
