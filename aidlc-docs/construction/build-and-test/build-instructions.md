# Build Instructions

## Prerequisites
- **Build Tool**: Docker + Docker Compose (v2, the `docker compose` plugin syntax used throughout — not the standalone `docker-compose` v1 binary)
- **Dependencies**: Nothing needs to be installed on the host beyond Docker itself — all language toolchains (Python 3.12, Node 20) run inside the build containers
- **Environment Variables**: Copy `.env.example` to `.env` and fill in real values (see below) — `docker compose` reads `.env` automatically
- **System Requirements**: Any machine that runs Docker Desktop (or Docker Engine on Linux); no unusual memory/disk requirements for a personal-scale deployment

## Required `.env` Values

| Variable | Where to get it |
|---|---|
| `DB_USER`, `DB_PASSWORD` | Choose your own values |
| `JWT_SECRET` | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Create an OAuth client at https://console.cloud.google.com/apis/credentials (type "Web application"; authorized redirect URI = `http://localhost:7878/drive/callback`, or whatever port you choose for `api-service`) |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| `FRONTEND_ORIGIN`, `API_BASE_URL` | Only change these together, and only if you change the host ports below — they must stay consistent with each other (CORS is locked to `FRONTEND_ORIGIN` exactly) |
| `GOOGLE_DRIVE_FOLDER_ID` | Defaults to the folder from the original project request; only override if scanning a different folder |

## Build Steps

### 1. Configure Environment
```bash
cp .env.example .env
# edit .env with real values per the table above
```

### 2. Build All Units
```bash
docker compose build
```
This builds 3 application images (`api-service`, `ingestion-worker`, `frontend`); `database` uses the stock `postgres:16-alpine` image, no build needed.

### 3. Start the Stack
```bash
docker compose up -d
```

### 4. Verify Build Success
- **Expected output of `docker compose ps`**: all 4 services show `healthy` (or, for `database`, simply `healthy` since it has no application code) within ~30-60 seconds of startup
- **Build artifacts**: 3 local Docker images (`transactagent-api-service`, `transactagent-ingestion-worker`, `transactagent-frontend`)
- **Common (harmless) warnings**: Vite prints `<script src="/config.js"> ... can't be bundled without type="module" attribute` during the frontend build — expected, `config.js` is generated at container startup, not at build time (see NFR Design's Runtime Config pattern)

## Troubleshooting

### `api-service` or `ingestion-worker` container exits immediately / unhealthy
- **Cause**: Alembic migration failure (check `docker compose logs api-service` or `docker compose logs ingestion-worker`) — usually a missing/incorrect `.env` value, or the `database` container not yet healthy when this one started
- **Solution**: Confirm `database` shows `healthy` first (`docker compose ps`); check the specific error in the logs; both backend units retry via `restart: unless-stopped`, so a transient DB-not-ready race resolves itself on retry

### `frontend` container shows `unhealthy` despite serving pages fine
- **Cause**: (Historical, already fixed in this codebase) An IPv4/IPv6 localhost resolution mismatch in the healthcheck — if you see this, confirm `docker-compose.yml`'s `frontend` healthcheck targets `http://127.0.0.1/`, not `http://localhost/`
- **Solution**: Already applied in the generated `docker-compose.yml`

### Build fails with dependency errors
- **Cause**: Usually a transient package-registry issue (PyPI/npm)
- **Solution**: Retry `docker compose build`; Docker's layer cache means only the failed step re-downloads
