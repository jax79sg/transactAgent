# Bank Transaction Insights

[![Database](https://github.com/jax79sg/transactAgent/actions/workflows/test-database.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/test-database.yml)
[![API Service](https://github.com/jax79sg/transactAgent/actions/workflows/test-api-service.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/test-api-service.yml)
[![Ingestion Worker](https://github.com/jax79sg/transactAgent/actions/workflows/test-ingestion-worker.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/test-ingestion-worker.yml)
[![Frontend](https://github.com/jax79sg/transactAgent/actions/workflows/test-frontend.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/test-frontend.yml)
[![Model Training](https://github.com/jax79sg/transactAgent/actions/workflows/lint-model-training.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/lint-model-training.yml)
[![Docker Build](https://github.com/jax79sg/transactAgent/actions/workflows/docker-build.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/docker-build.yml)
[![Secrets Scan](https://github.com/jax79sg/transactAgent/actions/workflows/secrets-scan.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/secrets-scan.yml)
[![Dependency Scan](https://github.com/jax79sg/transactAgent/actions/workflows/dependency-scan.yml/badge.svg)](https://github.com/jax79sg/transactAgent/actions/workflows/dependency-scan.yml)

A self-hosted, single-user web app that pulls your bank statement PDFs from a private Google Drive folder, extracts transactions with an LLM, auto-categorizes them (learning from your corrections over time), and gives you a filterable transaction table plus financial dashboards. Fully containerized — one `docker-compose up` runs the whole thing on your own machine.

📘 **[User Guide](https://jax79sg.github.io/transactAgent/)** — a screenshot walkthrough of every page (login, dashboard, transactions, Ask AI, ingestion, review, settings). Screenshots use AI-generated sample data, not real transactions.

## What it does

- **Manually-triggered ingestion**: you click "Run Ingestion" in the UI; nothing happens automatically or on a schedule
- **Layout-adaptive extraction**: reads PDF statements (including scanned/image-based ones) via Gemini's vision input — no per-bank parser code needed
- **Learned categorization**: matches new transactions against your past categorized ones first (fuzzy similarity, manual corrections weighted highest); falls back to an LLM classification constrained to your category whitelist; marks anything it's not confident about as `UNSURE`
- **Duplicate-proof**: re-running ingestion on the same statements never creates duplicate transactions
- **Multi-currency**: converts everything to SGD for dashboards, using the statement's own printed conversion when available, a public FX-rate API otherwise — original amounts always retained
- **Dashboards**: category spending trends, income vs. expenses, per-bank breakdowns
- **Ask AI**: ask a plain-language question about your own transaction history (e.g. "is this $33,000 outflow likely a transfer to my credit account?") and get an answer grounded in your real transaction data — scoped to a date range you pick, or your whole history. Each transaction also has a one-click "Ask AI" shortcut with a suggested question pre-filled.

## Architecture

Four containers, each independently deployable:

| Service | Role | Talks to |
|---|---|---|
| `database` | PostgreSQL — the only stateful service | — |
| `api-service` | REST API: auth, transactions, dashboards, category management, Google OAuth handshake | `database` |
| `ingestion-worker` | Background worker: Google Drive, statement extraction (Gemini), categorization (OpenRouter), FX conversion | `database`, Google Drive, Gemini, OpenRouter, exchangerate.host |
| `frontend` | React SPA (served by nginx) | `api-service` only |

`api-service` and `ingestion-worker` never call each other directly — they coordinate only through shared database rows (a queued "ingestion run" or "recategorization job"), so either can be restarted or redeployed independently.

Full design rationale and decision history: [`aidlc-docs/`](aidlc-docs/) (see `audit.md` for the complete build log, including every real bug found by actually running the code).

## Prerequisites

- Docker and Docker Compose (v2 — the `docker compose` command, not the standalone `docker-compose` binary)
- A Google Cloud project with an OAuth 2.0 Client ID (type "Web application")
- A [Google AI Studio](https://aistudio.google.com/apikey) API key (Gemini)
- An [OpenRouter](https://openrouter.ai/keys) API key (used with the free-tier `openrouter/free` router by default — no cost)

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | How to get it |
|---|---|
| `DB_USER`, `DB_PASSWORD` | Choose your own values |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Create OAuth client ID → Web application → authorized redirect URI `http://localhost:7878/drive/callback` (or whatever port you use for `api-service`) |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| `GOOGLE_DRIVE_FOLDER_ID` | Defaults to the folder from the original project setup — override if you want to scan a different Drive folder |
| `GEMINI_MODEL`, `OPENROUTER_MODEL` | Sensible free-tier defaults already set — override only if you want a different model (see `.env.example` for constraints) |
| `FRONTEND_ORIGIN`, `API_BASE_URL` | Only touch these together, and only if you change the host ports below — they must stay consistent with each other |

### 2. Build and start

```bash
docker compose build
docker compose up -d
docker compose ps    # wait until all 4 services show "healthy" (~30-60s)
```

### 3. Create your login

There's no self-registration (single-user app). Create your account with a single command, run entirely inside the `api-service` container (it already has the DB credentials and the hashing code — no need to export anything from `.env` into your own shell, and no bcrypt hash ever gets typed into a shell string, which avoids `$`-quoting issues):

```bash
docker exec transactagent-api python3 -c '
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from transactagent_db.migrate import build_database_url
from transactagent_db.models import User
from api_service.auth.security import hash_password

engine = create_engine(build_database_url())
with Session(engine) as session:
    session.add(User(username="your-username", password_hash=hash_password("choose-a-real-password")))
    session.commit()
print("User created.")
'
```

Edit `your-username` and `choose-a-real-password` before running. Keep the single quotes around the whole script (outer `'...'`) — they're what stop your shell from trying to interpret anything inside it; use plain characters in the password (avoid embedding a literal `'` in it).

### 4. Seed the category whitelist

```bash
docker exec transactagent-api python3 -m transactagent_db.seed_categories
```

Safe to re-run — only inserts categories that don't already exist. Edit the whitelist afterward from **Settings** in the app, or by editing `database/src/transactagent_db/seed_categories.py` before re-running.

### 5. Open the app

**http://localhost:8787** — log in with the username/password from step 3.

### 6. Connect Google Drive and run your first ingestion

**Settings → Connect Google Drive** → complete the Google consent screen → **Ingestion → Run Ingestion**. Watch live progress; check **Transactions** afterward for the extracted rows, and **Dashboard** for the charts.

## Stopping / Resetting

```bash
docker compose down        # stop containers, keep your data
docker compose down -v     # also wipe the database volume — full reset
```

Data persists in `./data/postgres` (bind-mounted, gitignored) between `docker compose up`/`down` cycles.

## Kubernetes Deployment (Alternative)

`docker-compose` above remains the recommended path for local development and stays
fully supported and unchanged — Kubernetes is an additional deployment option, not a
replacement.

A provider-agnostic Helm chart deploys all 5 services with HPA on the stateless
services, secrets via External Secrets Operator + HashiCorp Vault, and an Ingress —
see [`deploy/helm/transactagent/README.md`](deploy/helm/transactagent/README.md) for
the full walkthrough (prerequisites → secrets → install → create your login →
multi-device access). Live-verified end-to-end on a local [OrbStack](https://orbstack.dev/)
cluster, including a real login round-trip through the Ingress.

**Before deploying against a genuinely empty database**, see that guide's callout
about a pre-existing migration bug (PR #4) that must be merged first — otherwise the
app crash-loops on startup against a fresh database. Not Kubernetes-specific; it was
simply never exercised until a truly fresh database (a new PVC) hit it.

## Configuration Reference

See `.env.example` for the full list with inline explanations. A few worth knowing about:

- **`FRONTEND_ORIGIN` and `API_BASE_URL` must stay in sync** with the frontend's/API's actual host ports — CORS is locked to `FRONTEND_ORIGIN` exactly.
- **`GEMINI_MODEL`** must support image input (statement pages are always sent as images) — the default `gemini-3.5-flash-lite` does.
- **`OPENROUTER_MODEL`** should stay a free-tier model/router if you want to avoid charges — the default `openrouter/free` auto-routes across free-tier models.
- **`OPENROUTER_BASE_URL`** points the categorization LLM client at any OpenAI-compatible endpoint, not just OpenRouter — e.g. a local model server. If that server runs on your Mac (not in a container), `ingestion-worker` must reach it via `host.docker.internal`, not `127.0.0.1`/`localhost`, since the worker itself runs inside a container.
- **Ask AI** (`api-service`) reuses `GEMINI_API_KEY`/`GEMINI_MODEL` from the ingestion-worker settings above — one key, shared by both. `AI_ASSISTANT_MAX_TRANSACTIONS` (default 3000) caps how many transactions are sent as context per question.
- Ports default to `7878` (API) and `8787` (frontend) — chosen to avoid common local-dev port collisions; change them in `docker-compose.yml` if needed (and keep `FRONTEND_ORIGIN`/`API_BASE_URL`/`GOOGLE_OAUTH_REDIRECT_URI` in sync).

## Development

Each unit can be built and tested independently, without the full Docker stack:

```bash
# Backend units (each needs Docker running, for testcontainers' disposable Postgres)
cd database && pip install -e ".[test]" && pytest
cd api-service && pip install -e "../database" -e ".[test]" && pytest
cd ingestion-worker && pip install -e "../database" -e ".[test]" && pytest

# Frontend
cd frontend && npm install && npm test && npm run build
```

Full instructions, including integration-test scenarios and the complete list of bugs found and fixed by actually running this project end-to-end: [`aidlc-docs/construction/build-and-test/`](aidlc-docs/construction/build-and-test/).

## Troubleshooting

**`api-service` or `ingestion-worker` unhealthy / restarting** — check `docker compose logs api-service` (or `ingestion-worker`); usually a missing/wrong `.env` value, or the container started before `database` was ready (it retries automatically).

**Frontend loads but every action fails** — check that `FRONTEND_ORIGIN` (in `api-service`'s env) exactly matches the URL you're loading the app from; a mismatch is silently rejected by CORS.

**"Ingestion run already in progress" but nothing seems to be running** — check **Ingestion** page run history; if a run is genuinely stuck, check `docker compose logs ingestion-worker` for errors.

More detail: [`aidlc-docs/construction/build-and-test/build-instructions.md`](aidlc-docs/construction/build-and-test/build-instructions.md).

## Project Structure

```
database/            Unit 1 — schema, migrations (SQLAlchemy + Alembic), no runtime service
api-service/          Unit 2 — FastAPI REST API
ingestion-worker/       Unit 3 — background worker (Drive, extraction, categorization, FX)
frontend/                Unit 4 — React SPA
docker-compose.yml         Orchestrates all 4 services (recommended for local dev)
deploy/                      Kubernetes Helm chart, cluster prerequisites, deploy scripts
.env.example                   Full configuration reference
aidlc-docs/                      Design docs, requirements, decision history, audit trail
```
