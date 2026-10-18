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
  accounts/               # Epic 13: list, rename/retype, anchor, merge
  balances/               # Epic 13: balance on a date, balance over time, discrepancies (calculation.py is pure)
  health.py               # /health
```

Epic 14 (Probable Duplicate Statement Detection) is described in [probable-duplicate-summary.md](probable-duplicate-summary.md).

Epic 13 (Account Balance at a Point in Time, the API side) is described in [account-balance-summary.md](account-balance-summary.md).

### Property-based tests

The balance arithmetic has property-based tests (Hypothesis). `tests/conftest.py` registers two profiles: `dev` (random examples; a failure prints the blob that replays it exactly) and `ci` (derandomized, so every CI run is identical; chosen automatically when the `CI` environment variable is set, as GitHub Actions does). To replay a failing property: run the same test with `CI=1` to get the same examples, or paste the printed `@reproduce_failure(...)` line above the test; shrinking is never disabled, so the failure shown is already the smallest found.
