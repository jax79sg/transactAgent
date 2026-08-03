# Infrastructure Design — Unit 2: API Service

## Docker Compose Service: `api-service`

```yaml
services:
  api-service:
    build:
      context: .
      dockerfile: api-service/Dockerfile
    container_name: transactagent-api
    environment:
      DB_HOST: database
      DB_PORT: "5432"
      DB_NAME: ${DB_NAME:-transactagent}
      DB_USER: ${DB_USER}
      DB_PASSWORD: ${DB_PASSWORD}
      JWT_SECRET: ${JWT_SECRET}
      FRONTEND_ORIGIN: ${FRONTEND_ORIGIN:-http://localhost:5173}
    ports:
      - "7878:8000"
    depends_on:
      database:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    networks:
      - transactagent-net
```

**Notes**:
- **Build context is the workspace root** (`.`), not `./api-service` — the Dockerfile needs to `COPY` the sibling `database/` package (Unit 1) into the image, which is outside a `./api-service`-scoped build context. Corrected during Code Generation (2026-08-01) after the Dockerfile was written and this dependency became concrete; the original draft here during Infrastructure Design hadn't yet accounted for it.
- **Host port 7878 -> container port 8000** (Question 1 = B — user-selected to avoid a local conflict; Uvicorn listens on 8000 inside the container regardless).
- **`depends_on: database: condition: service_healthy`** — reuses Unit 1's healthcheck-based ordering pattern.
- **Own healthcheck** hits the `/health` endpoint (NFR Design) so Unit 4 can, in turn, depend on this service being ready.
- **`JWT_SECRET`** is a new required secret (NFR-4.1) — added to `.env.example` below; must be a long random string, generated once and kept stable (rotating it invalidates all active sessions).
- **`FRONTEND_ORIGIN`** feeds the CORS policy (NFR Design Question 1 = A); defaults to a placeholder that will be confirmed once Unit 4's Infrastructure Design finalizes the Frontend's actual port.
- **No volume** — this is a stateless service; all persistent state lives in the `database` service.

## Required Environment Variables (added to `.env.example`)

```
JWT_SECRET=changeme-generate-a-long-random-string
FRONTEND_ORIGIN=http://localhost:5173
```
