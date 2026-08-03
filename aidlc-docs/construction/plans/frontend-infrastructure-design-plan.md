# Infrastructure Design Plan — Unit 4: Frontend SPA

**Input**: `aidlc-docs/construction/frontend/nfr-design/` (approved)

## Infrastructure Category Assessment

| Category | Assessment |
|---|---|
| Deployment Environment | Fixed: local docker-compose |
| Compute Infrastructure | Multi-stage Docker build: Node build stage (Vite production build) -> **nginx** serve stage (lightweight, standard for static SPA hosting, well-supported client-side-routing fallback config for React Router) — decided directly |
| Storage Infrastructure | N/A — stateless static assets |
| Messaging Infrastructure | N/A |
| Networking Infrastructure | **Real decision**: this is the main browser-facing entry point to the whole app, so it needs a host port. Question below (which port). |
| Monitoring Infrastructure | N/A — a simple nginx healthcheck (`curl localhost/`) is sufficient, decided directly, no question needed |
| Shared Infrastructure | `depends_on: api-service (healthy)`; **important cross-cutting note**: whatever port is chosen here must exactly match Unit 2's `FRONTEND_ORIGIN` env var (CORS is locked to that exact origin) — both `.env.example` entries will be kept in sync |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (host port) — Answer: custom, 8787
- [x] Step 2: Generate `infrastructure-design.md` — the `frontend` docker-compose service definition, and the nginx config for SPA routing + the runtime config.js generation entrypoint
- [x] Step 3: Update the shared `deployment-architecture.md` with Unit 4's finalized entry (completing the full topology) — all 4 units now finalized

## Clarifying Question

### Question 1 — Host Port
Which host port should the Frontend be exposed on (`http://localhost:<port>`)? This is the URL you'll actually open in your browser to use the app.

A) **5173** (Vite's dev-server convention — familiar if you've used Vite before, even though this is a production nginx-served build, not the dev server)

B) **3000** (common general-purpose frontend convention)

C) **80** (standard HTTP port — lets you open `http://localhost` with no port number at all)

X) Other (please describe after [Answer]: tag below)

[Answer]:X. 8787

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done. Whatever you choose here, I'll update `FRONTEND_ORIGIN` in `.env.example` to match exactly, since Unit 2's CORS policy is locked to that origin.
