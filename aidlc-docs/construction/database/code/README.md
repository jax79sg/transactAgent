# Unit 1: Database — Package Overview

`database/` at the workspace root is a standalone Python package (`transactagent_db`) providing the shared schema for the whole application. It has no runtime service of its own — Units 2 (API Service) and 3 (Ingestion Worker Service) both depend on it directly.

## Contents

- `src/transactagent_db/models.py` — SQLAlchemy 2.0 declarative models (single source of truth for the schema)
- `src/transactagent_db/migrate.py` — `build_database_url()` and `run_migrations_with_lock()`, imported by Units 2/3's entrypoints
- `src/transactagent_db/seed_categories.py` — idempotent category-whitelist seeding
- `migrations/` — Alembic environment and versioned migration scripts
- `tests/` — model/constraint tests (testcontainers-backed Postgres)

## How Units 2 and 3 Depend On This Package

Both units install this package as a local editable dependency (e.g., `pip install -e ../database` inside their own container build, or equivalent monorepo-relative path dependency), then:

```python
from transactagent_db.migrate import run_migrations_with_lock
from transactagent_db.models import Transaction, Category, Base  # etc.

run_migrations_with_lock(alembic_ini_path="../database/alembic.ini")  # first line of entrypoint
```

## Running Locally (development)

```bash
cd database
pip install -e ".[test]"
export DB_USER=transactagent_app DB_PASSWORD=changeme DB_HOST=localhost DB_PORT=5432 DB_NAME=transactagent
alembic upgrade head
python -m transactagent_db.seed_categories
pytest
```

(`pytest` spins up its own disposable Postgres via testcontainers — it does not require the `alembic upgrade head` step above.)
