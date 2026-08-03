"""Reusable migration entrypoint for Units 2 and 3.

Implements the NFR Design "auto-migrate on startup with advisory-lock safety" pattern:
each backend unit calls run_migrations_with_lock() as the first step of its own
container entrypoint, before serving requests or polling for jobs.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

# Arbitrary, fixed 64-bit advisory lock ID reserved for schema migrations. Any
# int64 value works as long as it's consistent across both backend units and
# not reused for an unrelated purpose elsewhere in the system.
MIGRATION_ADVISORY_LOCK_ID = 7_735_281_940_001


def build_database_url() -> str:
    host = os.environ.get("DB_HOST", "database")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "transactagent")
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def run_migrations_with_lock(alembic_ini_path: str | Path) -> None:
    """Acquire a Postgres advisory lock, run `alembic upgrade head`, then release it.

    Safe to call concurrently from multiple containers at startup: the second
    caller blocks until the first finishes, then runs upgrade() again as a no-op
    (Alembic's alembic_version table means an already-current schema is a
    fast, safe no-op).

    Fails fast (raises) on any migration error, per the NFR Design fail-fast pattern
    -- callers should let this exception propagate and crash the container rather
    than catching it and continuing.
    """
    engine = create_engine(build_database_url())
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_ADVISORY_LOCK_ID})
        try:
            _run_alembic_upgrade(alembic_ini_path)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_ADVISORY_LOCK_ID}
            )
    engine.dispose()


def _run_alembic_upgrade(alembic_ini_path: str | Path) -> None:
    # alembic.ini's `script_location = migrations` is resolved relative to the
    # subprocess's CURRENT WORKING DIRECTORY, not relative to the ini file's own
    # location -- passing -c <path> alone is not enough. Without cwd set here, this
    # only works when the caller's WORKDIR happens to already be the database/
    # directory; both Units 2 and 3 set WORKDIR to their own package instead, so this
    # failed with "Path doesn't exist: migrations" the moment it ran for real inside a
    # container (caught by actually running `docker compose up`, not by the
    # testcontainers-based unit tests, which bypass this subprocess path entirely via
    # run_migrations=False).
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini_path), "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=Path(alembic_ini_path).resolve().parent,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migration failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
