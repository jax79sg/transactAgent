# Infrastructure Design — Unit 3: Ingestion Worker Service

## Docker Compose Service: `ingestion-worker`

```yaml
services:
  ingestion-worker:
    build:
      context: .
      dockerfile: ingestion-worker/Dockerfile
    container_name: transactagent-worker
    environment:
      DB_HOST: database
      DB_PORT: "5432"
      DB_NAME: ${DB_NAME:-transactagent}
      DB_USER: ${DB_USER}
      DB_PASSWORD: ${DB_PASSWORD}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      GEMINI_MODEL: ${GEMINI_MODEL:-gemini-3.1-flash-lite}
      OPENROUTER_MODEL: ${OPENROUTER_MODEL:-openrouter/free}
      GOOGLE_OAUTH_CLIENT_ID: ${GOOGLE_OAUTH_CLIENT_ID}
      GOOGLE_OAUTH_CLIENT_SECRET: ${GOOGLE_OAUTH_CLIENT_SECRET}
      GOOGLE_DRIVE_FOLDER_ID: ${GOOGLE_DRIVE_FOLDER_ID:-1qeJblYSk-E6BH6dhenbc8Vd0xxRkZor0}
      HEARTBEAT_FILE: /tmp/worker-heartbeat
    depends_on:
      database:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "find /tmp/worker-heartbeat -mmin -0.5 | grep -q ."]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped
    networks:
      - transactagent-net
```

**Notes**:
- **No `ports:` mapping** — nothing calls into this service directly (Question in Infrastructure Design plan — no networking exposure needed).
- **Build context is the workspace root** (`.`), same reasoning as Unit 2's Dockerfile — needs to `COPY` the sibling `database/` package.
- **Healthcheck** (Question 1 = A): the worker loop touches `HEARTBEAT_FILE` on every poll cycle (every 5s per NFR Design); the healthcheck's `find -mmin -0.5` checks the file was modified within the last 30 seconds. Three missed heartbeats (45s of no progress) marks the container unhealthy, visible in `docker compose ps`.
- **`depends_on: database: condition: service_healthy`** — reused pattern.
- **No `FRONTEND_ORIGIN`/`JWT_SECRET`** — this service has no HTTP surface, so those Unit-2-specific concerns don't apply here.
- **New secrets**: `GEMINI_API_KEY`, `OPENROUTER_API_KEY`. **Correction (2026-08-01, caught while implementing the Drive client)**: `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` ARE also needed here, contrary to what was first assumed — refreshing an access token via Google's stored refresh token requires the OAuth client credentials in the refresh request itself, not just the refresh token. Same OAuth client as Unit 2, not a separate one. `GOOGLE_DRIVE_FOLDER_ID` also added (defaults to the folder from the original project request).
- **Model IDs are configuration, not code** (2026-08-01 per user request): `GEMINI_MODEL` and `OPENROUTER_MODEL` are read by `config.py` (not hardcoded in the client wrappers), so switching models never requires a rebuild.

## Required Environment Variables (added to `.env.example`)

```
GEMINI_API_KEY=changeme
OPENROUTER_API_KEY=changeme
GEMINI_MODEL=gemini-3.1-flash-lite
OPENROUTER_MODEL=openrouter/free
```
