"""Worker loop entrypoint (NFR Design: simple asyncio poll, 5s interval, one
run/job at a time -- WR-8).
"""

import asyncio
import logging
from pathlib import Path

from ingestion_worker.config import settings
from ingestion_worker.db import session_scope
from ingestion_worker.heartbeat import touch_heartbeat
from ingestion_worker.logging_capture import DbLogHandler
from ingestion_worker.orchestrator import pipeline, repository
from transactagent_db.migrate import run_migrations_with_lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DATABASE_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "database" / "alembic.ini"


def poll_once() -> None:
    """One poll cycle: claim and fully process at most one queued IngestionRun,
    then at most one queued RecategorizationJob. Never processes two of either
    concurrently (WR-8)."""
    with session_scope() as db:
        run = repository.find_queued_run(db)
        if run is not None:
            repository.claim_run(db, run)
            # session_scope() commits this claim on clean exit from this `with` block,
            # before we re-open a new session below to actually process it.

    if run is not None:
        with session_scope() as db:
            run = db.merge(run)
            pipeline.process_run(db, run)
        return  # one run per poll cycle -- don't also pick up a job this cycle

    with session_scope() as db:
        job = repository.find_queued_recategorize_job(db)
        if job is not None:
            repository.claim_recategorize_job(db, job)

    if job is not None:
        with session_scope() as db:
            job = db.merge(job)
            pipeline.process_recategorize_job(db, job)


async def run_forever() -> None:
    run_migrations_with_lock(_DATABASE_ALEMBIC_INI)
    # Attached here, not at module import time: it opens real DB connections when
    # triggered, which must never happen as a side effect of merely importing this
    # module (e.g. test_main_loop.py imports `main` and calls poll_once() directly,
    # without a real database available -- caught before it could make every test that
    # exercises pipeline.process_run() attempt, and fail, a real DB connection per log
    # line). Attached to the root logger (not just this module's) so the live log-tail
    # view captures the same output a user watching `docker compose logs` would see --
    # googleapiclient, httpx, openai, google-genai included, not just this codebase's
    # own logger.info() calls.
    logging.getLogger().addHandler(DbLogHandler())
    logger.info("Ingestion worker started, polling every %ss", settings.poll_interval_seconds)
    while True:
        touch_heartbeat()
        try:
            poll_once()
        except Exception:  # noqa: BLE001 - a bug in one poll cycle must not kill the worker process
            logger.exception("Unhandled error during poll cycle")
        await asyncio.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_forever())
