# Unit 2: API Service — Package Overview

FastAPI backend serving the Frontend SPA (Unit 4). Depends on Unit 1's `database` package for models and migrations.

## Running Locally (development, without docker-compose)

```bash
cd api-service
pip install -e ".[test]"
export DB_USER=transactagent_app DB_PASSWORD=changeme DB_HOST=localhost DB_PORT=5432 DB_NAME=transactagent
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export FRONTEND_ORIGIN=http://localhost:5173
uvicorn api_service.main:app --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`.

## Running Tests

```bash
pip install -e ".[test]"
pytest
```

Tests spin up a disposable Postgres via testcontainers (requires Docker) and never touch the real `database` service.

## Structure

```
api-service/src/api_service/
  main.py              # app instantiation, CORS, lifespan migration, router registration
  config.py            # env-sourced settings
  db.py                # DB session-per-request dependency
  errors.py            # typed business-rule exceptions -> consistent error responses
  schemas.py            # shared CamelModel base
  auth/                # login, JWT issue/validate, password hashing
  transactions/         # list/filter/group, manual correction, CSV export
  dashboards/            # category trends, cash flow, bank breakdown
  ingestion/              # trigger/status/history
  categories/             # whitelist CRUD
  health.py               # /health
```
