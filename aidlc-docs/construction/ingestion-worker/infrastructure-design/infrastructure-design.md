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
      GOOGLE_DRIVE_FOLDER_ID: ${GOOGLE_DRIVE_FOLDER_ID}
      GOOGLE_DRIVE_BACKUP_FOLDER_ID: ${GOOGLE_DRIVE_BACKUP_FOLDER_ID}
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

## Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9)

### New Docker Compose Service: `vector-db`

```yaml
services:
  vector-db:
    image: qdrant/qdrant:latest
    container_name: transactagent-vector-db
    volumes:
      - ./data/qdrant:/qdrant/storage
    healthcheck:
      # qdrant/qdrant's image has neither wget nor curl (verified by actually running the image and
      # checking) -- bash IS present, so a raw /dev/tcp connect is the simplest reliable check.
      test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/127.0.0.1/6333' || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    networks:
      - transactagent-net
```

**Notes**:
- **No `ports:` mapping** — only `ingestion-worker` talks to it (same reasoning as `ingestion-worker` itself).
- **Bind-mounted volume** (`./data/qdrant`), same durability pattern as `database`'s `./data/postgres`.
- **Healthcheck**: originally planned as `wget --spider` against `/healthz` (matching the `frontend`
  healthcheck's tool), but actually running `qdrant/qdrant:latest` (Debian trixie-based) showed it has
  **neither `wget` nor `curl`** — only `bash`. Caught before Code Generation by pulling and inspecting the
  real image rather than assuming Alpine-style tooling. Switched to a `bash`-native `/dev/tcp` TCP-connect
  check — simpler than the alternative (rolling a full HTTP request via `/dev/tcp` and grepping the response),
  and a listening port is a sufficient liveness signal at this stack's scale (same level of rigor as
  `database`'s `pg_isready`, not a full HTTP round-trip like `api-service`'s healthcheck).

### `ingestion-worker` Service Additions

```yaml
    environment:
      # ...existing vars unchanged...
      QDRANT_HOST: vector-db
      QDRANT_PORT: "6333"
      EMBEDDING_BASE_URL: ${EMBEDDING_BASE_URL:-}
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-embeddinggemma-300m}
      EMBEDDING_SIMILARITY_THRESHOLD: ${EMBEDDING_SIMILARITY_THRESHOLD:-0.75}
      EMBEDDING_TOP_K: ${EMBEDDING_TOP_K:-5}
      EMBEDDING_BATCH_SIZE: ${EMBEDDING_BATCH_SIZE:-50}
      EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-768}
    depends_on:
      database:
        condition: service_healthy
      vector-db:
        condition: service_healthy
```

- **`EMBEDDING_BASE_URL` has no working default** (empty string) — unlike `OPENROUTER_BASE_URL`, there is no
  hosted fallback; it's entirely user-managed (NFR-5). An empty/unset value is treated by the application the
  same as an unreachable endpoint (WR-25 soft-fail), not a startup error (NFR Design's non-blocking-startup
  principle extends to config, not just the Qdrant connection).
- **`depends_on: vector-db: condition: service_healthy`** only orders container *startup*, consistent with
  NFR Design's non-blocking-startup pattern — the worker's own code still tolerates `vector-db` being
  unreachable after startup (a restart, a manual `docker compose stop vector-db`, etc.).
- **oMLX itself gets no `docker-compose` entry** — host-native, user-managed prerequisite (NFR-5, Documented
  Assumption #2), exactly like the categorization-LLM-fallback oMLX instance already in use via
  `OPENROUTER_BASE_URL`.

### `.env.example` Additions

```
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=embeddinggemma-300m
EMBEDDING_SIMILARITY_THRESHOLD=0.75
EMBEDDING_TOP_K=5
EMBEDDING_BATCH_SIZE=50
EMBEDDING_DIMENSIONS=768
```
