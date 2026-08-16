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

---

## Addendum (2026-08-16, Configurable Application Settings feature)

Tracked here per the approved execution plan (`configurable-app-settings-execution-plan.md`) — this feature's Infrastructure Design work is scoped to the Ingestion Worker Service unit, but covers `docker-compose.yml` holistically since it touches both `api-service` and `ingestion-worker`'s service blocks together (the new volume is shared by both).

### New Shared Volume: `settings-override`

A new, small, named Docker volume — not a bind mount (unlike `./data/postgres`/`./data/qdrant`) — bind-mounted at the same container path in both `api-service` and `ingestion-worker`:

```yaml
volumes:
  settings-override:
```

```yaml
  api-service:
    # ...existing config unchanged...
    volumes:
      - settings-override:/config/overrides
  ingestion-worker:
    # ...existing config unchanged...
    volumes:
      - settings-override:/config/overrides
```

**Notes**:
- **Named volume, not a bind mount**: unlike `./data/postgres`/`./data/qdrant` (deliberately bind-mounted so the user can inspect/back up real financial data directly), the override file holds only non-secret application tuning values with no standalone value to the user outside the running app — a named volume keeps it out of the project directory entirely, avoiding any risk of it being accidentally committed or confused with `.env` (both plaintext files, easy to mix up if co-located on the host filesystem).
- **`/config/overrides` is a directory, not a single file path**: the Configuration Component (API Service) writes one file inside it (exact filename is a Code Generation detail, e.g. `settings.env`); mounting the parent directory rather than a single file avoids Docker's bind-mount-of-a-nonexistent-file edge cases on first-ever startup (a named volume mounted as a directory is always creatable; a named volume mounted as a single nonexistent file path is not, without extra setup).
- **No `depends_on` implication**: this is passive shared state, not a service — neither container needs the other running to read or write it (consistent with `services.md`'s "not a direct call" framing).

### Closing the Pre-Existing Env-Mapping Gap

Per `configurable-app-settings-requirements.md`'s "Current Behavior" section, `ingestion-worker`'s `environment:` block was missing mappings for several settings that already existed in `config.py`/`.env.example`. FR-CAS-5 requires this closed for every one of the 35 settings this feature exposes (regardless of the override-file mechanism, WR-33, which layers on top and needs no compose change of its own — see that WR's own note that it doesn't depend on this gap being closed). The following are added to `ingestion-worker`'s `environment:` block (previously absent entirely):

```yaml
      SIMILARITY_THRESHOLD: ${SIMILARITY_THRESHOLD:-85.0}
      SIMILARITY_AMOUNT_RATIO_TOLERANCE: ${SIMILARITY_AMOUNT_RATIO_TOLERANCE:-4.0}
      SIMILARITY_AMOUNT_ABSOLUTE_FLOOR: ${SIMILARITY_AMOUNT_ABSOLUTE_FLOOR:-5.0}
      RECATEGORIZATION_AUTO_APPLY_THRESHOLD: ${RECATEGORIZATION_AUTO_APPLY_THRESHOLD:-97.0}
      EXTRACTION_CONFIDENCE_THRESHOLD: ${EXTRACTION_CONFIDENCE_THRESHOLD:-medium}
      POLL_INTERVAL_SECONDS: ${POLL_INTERVAL_SECONDS:-5.0}
      RETRY_MAX_ATTEMPTS: ${RETRY_MAX_ATTEMPTS:-3}
      RETRY_BACKOFF_BASE_SECONDS: ${RETRY_BACKOFF_BASE_SECONDS:-2.0}
      REPORTING_CURRENCY: ${REPORTING_CURRENCY:-SGD}
      RECURRING_PAYMENT_MATCH_WINDOW_DAYS: ${RECURRING_PAYMENT_MATCH_WINDOW_DAYS:-5}
      RECURRING_PAYMENT_TRUSTED_AMOUNT_RATIO_TOLERANCE: ${RECURRING_PAYMENT_TRUSTED_AMOUNT_RATIO_TOLERANCE:-1.15}
      RECURRING_PAYMENT_TRUSTED_AMOUNT_ABSOLUTE_FLOOR: ${RECURRING_PAYMENT_TRUSTED_AMOUNT_ABSOLUTE_FLOOR:-5.0}
      RECURRING_PAYMENT_DETECTION_SCAN_INTERVAL_HOURS: ${RECURRING_PAYMENT_DETECTION_SCAN_INTERVAL_HOURS:-24}
      RECURRING_PAYMENT_DETECTION_MIN_OCCURRENCES: ${RECURRING_PAYMENT_DETECTION_MIN_OCCURRENCES:-2}
      RECURRING_PAYMENT_DETECTION_CADENCE_MIN_DAYS: ${RECURRING_PAYMENT_DETECTION_CADENCE_MIN_DAYS:-25}
      RECURRING_PAYMENT_DETECTION_CADENCE_MAX_DAYS: ${RECURRING_PAYMENT_DETECTION_CADENCE_MAX_DAYS:-35}
      LLM_CLASSIFICATION_BATCH_SIZE: ${LLM_CLASSIFICATION_BATCH_SIZE:-10}
      LLM_CLASSIFICATION_CONCURRENCY: ${LLM_CLASSIFICATION_CONCURRENCY:-5}
      EMBEDDING_PRICE_BUCKET_BOUNDARIES: ${EMBEDDING_PRICE_BUCKET_BOUNDARIES:-1,5,10,20,50,100,200,500,1000,2000,5000}
      EMBEDDING_LLM_AGREEMENT_BOOST: ${EMBEDDING_LLM_AGREEMENT_BOOST:-0.05}
      BACKUP_SCHEDULE_HOUR: ${BACKUP_SCHEDULE_HOUR:-2}
      BACKUP_RETENTION_COUNT: ${BACKUP_RETENTION_COUNT:-7}
```

And on `api-service`'s `environment:` block:

```yaml
      JWT_EXPIRY_MINUTES: ${JWT_EXPIRY_MINUTES:-1440}
      DEFAULT_PAGE_SIZE: ${DEFAULT_PAGE_SIZE:-50}
      MAX_PAGE_SIZE: ${MAX_PAGE_SIZE:-200}
      CSV_EXPORT_MAX_ROWS: ${CSV_EXPORT_MAX_ROWS:-50000}
      RECURRING_PAYMENT_DUE_SOON_LEAD_DAYS: ${RECURRING_PAYMENT_DUE_SOON_LEAD_DAYS:-5}
      GOOGLE_OAUTH_REDIRECT_URI: ${GOOGLE_OAUTH_REDIRECT_URI:-http://localhost:7878/drive/callback}
```

(`GOOGLE_OAUTH_REDIRECT_URI` was already mapped on `api-service` before this feature — listed here only because it's one of the 35 in-scope settings, for completeness; no change to its existing line.) `QDRANT_HOST`/`QDRANT_PORT` are already mapped (Epic 9) and stay as-is — both are in-scope (Advanced) but already correctly flowing today. `EMBEDDING_API_KEY` stays excluded (secret) and unmapped-by-this-feature, consistent with NFR-CAS-2 — it is never added to any allow-list the Configuration Component consults.

**Rationale for using the exact same `${VAR:-default}` compose pattern as every existing mapping, not something new**: WR-33's `settings_customise_sources()` mechanism gives the override file unconditional priority regardless of what process env supplies — so closing this gap the ordinary way (matching every other existing mapping in this file) is sufficient; no special-casing needed here to make the override mechanism work, keeping this change a plain, easily-reviewable diff.
