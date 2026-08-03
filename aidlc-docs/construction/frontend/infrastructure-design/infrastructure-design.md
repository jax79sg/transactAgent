# Infrastructure Design — Unit 4: Frontend SPA

## Docker Compose Service: `frontend`

```yaml
services:
  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    container_name: transactagent-frontend
    environment:
      API_BASE_URL: ${API_BASE_URL:-http://localhost:7878}
    ports:
      - "8787:80"
    depends_on:
      api-service:
        condition: service_healthy
    healthcheck:
      # nginx:alpine has no curl (corrected during Code Generation); Alpine's busybox
      # includes wget by default. 127.0.0.1, not "localhost" (corrected during Build
      # and Test after actually running the container): Alpine's resolver tries ::1
      # first, and nginx.conf only binds IPv4, so "localhost" got "connection refused"
      # despite the exact same request succeeding fine from the host.
      test: ["CMD", "wget", "--quiet", "--spider", "http://127.0.0.1/"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    networks:
      - transactagent-net
```

**Notes**:
- **Host port 8787 -> container port 80** (nginx's default). Question 1 = custom (8787).
- **`API_BASE_URL`**: consumed by the container's entrypoint script to generate `config.js` at startup (NFR Design's Runtime Config pattern) — defaults to `http://localhost:7878`, matching Unit 2's own host port, since the browser (not the container network) is what actually calls the API.
- **`depends_on: api-service: condition: service_healthy`** — reused pattern.
- **Cross-cutting sync requirement**: `FRONTEND_ORIGIN` (Unit 2's CORS allow-list) MUST equal `http://localhost:8787` exactly. Updated in `.env.example` accordingly.
- **No volume** — stateless static assets, rebuilt into the image.

## Multi-Stage Dockerfile Approach (implemented in Code Generation)

1. **Build stage**: Node image, `npm ci && npm run build` -> produces `dist/`
2. **Serve stage**: `nginx:alpine`, copies `dist/` in, custom nginx config with a catch-all fallback to `index.html` (required for React Router's client-side routes to work on a hard refresh/direct URL visit), entrypoint script writes `config.js` from `API_BASE_URL` before nginx starts

## Required Environment Variables (added to `.env.example`)

```
API_BASE_URL=http://localhost:7878
```

(`FRONTEND_ORIGIN` in the API Service section is updated to `http://localhost:8787` to match.)
