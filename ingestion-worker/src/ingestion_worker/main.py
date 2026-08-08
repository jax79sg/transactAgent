"""Worker loop entrypoint (NFR Design: simple asyncio poll, 5s interval, one
run/job at a time -- WR-8).
"""

import asyncio
import logging
from pathlib import Path

from ingestion_worker.backup import service as backup_service
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
    then at most one queued RecategorizationJob, then (Epic 7) a nightly backup if
    one is due. Never processes two of the three concurrently (WR-8, WR-11) --
    each branch only runs when every branch before it found nothing to do."""
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
        return  # one run per poll cycle -- don't also pick up a job or backup this cycle

    with session_scope() as db:
        job = repository.find_queued_recategorize_job(db)
        if job is not None:
            repository.claim_recategorize_job(db, job)

    if job is not None:
        with session_scope() as db:
            job = db.merge(job)
            pipeline.process_recategorize_job(db, job)
        return  # one job per poll cycle -- don't also check for a backup this cycle

    with session_scope() as db:
        if backup_service.is_backup_due_now(db):
            backup_service.run_backup(db)


def recover_stale_state() -> None:
    """Called once at startup, before the poll loop begins: a fresh process starting
    up can only mean any previous process is gone, so any IngestionRun/
    RecategorizationJob left QUEUED/RUNNING is orphaned, not genuinely in progress
    (WR-8: single worker, one run at a time). Left alone, an orphaned "running" run
    blocks every future run forever via ingestion_runs' single-active-run unique
    constraint -- confirmed live: a categorization call hung indefinitely
    (2026-08-04, see aidlc-docs/audit.md), and recovering required manual DB
    surgery. This makes a plain restart self-heal instead.
    """
    with session_scope() as db:
        stale_runs = repository.fail_stale_runs(db)
        stale_jobs = repository.fail_stale_recategorize_jobs(db)
    if stale_runs or stale_jobs:
        logger.warning(
            "Startup recovery: marked %d orphaned ingestion run(s) and %d orphaned "
            "recategorization job(s) as failed (left over from a previous process)",
            stale_runs, stale_jobs,
        )


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

    recover_stale_state()

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
