from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
)


def fail_stale_runs(db: Session) -> int:
    """Marks any IngestionRun left in QUEUED or RUNNING as FAILED. Meant to be
    called once at worker startup, before the poll loop begins: this is a
    single-worker system (WR-8, one run at a time) with a DB-level unique
    constraint enforcing at most one active (queued/running) run, so any such row
    still present when a fresh process starts can only be orphaned -- left behind
    by a previous process that died or hung without ever reaching complete_run/
    fail_run, rather than genuinely still being worked on by anyone.

    Without this, an orphaned "running" row blocks EVERY future run forever (the
    unique constraint rejects new ones), requiring manual DB surgery to recover --
    confirmed live: a categorization call to a local model server hung
    indefinitely (2026-08-04, see aidlc-docs/audit.md), leaving a run stuck
    "running" with no live process ever going to finish it. A restart now
    self-heals instead.
    """
    stale = db.scalars(
        select(IngestionRun).where(IngestionRun.status.in_([IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING]))
    ).all()
    for run in stale:
        fail_run(db, run)
    return len(stale)


def fail_stale_recategorize_jobs(db: Session) -> int:
    """Same reasoning as fail_stale_runs, applied to RecategorizationJob: a job
    left QUEUED/RUNNING when a fresh worker process starts can only be orphaned.
    Unlike ingestion runs, jobs don't have a single-active-job DB constraint, so an
    orphaned job doesn't lock out future jobs -- but it would still sit unresolved
    forever with no automatic re-queue, so it's cleaned up here too for the same
    self-healing-on-restart behavior.
    """
    stale = db.scalars(
        select(RecategorizationJob).where(
            RecategorizationJob.status.in_([RecategorizationJobStatus.QUEUED, RecategorizationJobStatus.RUNNING])
        )
    ).all()
    for job in stale:
        fail_recategorize_job(db, job)
    return len(stale)


def find_queued_run(db: Session) -> IngestionRun | None:
    return db.scalar(select(IngestionRun).where(IngestionRun.status == IngestionRunStatus.QUEUED))


def claim_run(db: Session, run: IngestionRun) -> None:
    run.status = IngestionRunStatus.RUNNING
    db.commit()


def update_run_progress(
    db: Session,
    run: IngestionRun,
    *,
    files_found: int | None = None,
    processed_delta: int = 0,
    skipped_delta: int = 0,
    failed_delta: int = 0,
) -> None:
    # Commits (not just flushes) so the API service's own DB connection -- a separate
    # process, in a separate transaction -- actually sees monotonically-increasing
    # progress while the run is in flight, per the approved Functional Design
    # (domain-entities.md) and the Frontend's ActiveRunProgress polling component
    # (US-1.2's "near-live" requirement). Previously the whole run ran inside one
    # long-lived session that only committed at the very end, so the UI showed
    # "Running, 0 found" for the entire run's duration -- caught by a user watching
    # the UI and seeing no progress (aidlc-docs/audit.md).
    if files_found is not None:
        run.files_found_count = files_found
    run.files_processed_count += processed_delta
    run.files_skipped_count += skipped_delta
    run.files_failed_count += failed_delta
    db.commit()


def complete_run(db: Session, run: IngestionRun) -> None:
    from datetime import datetime

    run.status = (
        IngestionRunStatus.COMPLETED_WITH_FAILURES if run.files_failed_count > 0 else IngestionRunStatus.COMPLETED
    )
    run.completed_at = datetime.now(UTC)
    db.commit()


def fail_run(db: Session, run: IngestionRun) -> None:
    from datetime import datetime

    run.status = IngestionRunStatus.FAILED
    run.completed_at = datetime.now(UTC)
    db.commit()


def is_cancellation_requested(db: Session, run_id) -> bool:
    """Checked between files (never mid-file) by the pipeline's main loop. A plain
    scalar query rather than touching the caller's ORM-managed `run` object: the API
    writes `cancel_requested_at` from a separate process/transaction, and the
    previous file's update_run_progress() commit already ended this session's prior
    transaction, so a fresh query here (READ COMMITTED) reliably sees it as soon as
    the API's own commit lands -- no explicit refresh/merge needed."""
    return (
        db.scalar(select(IngestionRun.cancel_requested_at).where(IngestionRun.id == run_id)) is not None
    )


def cancel_run(db: Session, run: IngestionRun) -> None:
    from datetime import datetime

    run.status = IngestionRunStatus.CANCELLED
    run.completed_at = datetime.now(UTC)
    db.commit()


def record_run_file(
    db: Session,
    run: IngestionRun,
    *,
    drive_file_id: str,
    drive_file_name: str,
    outcome: IngestionRunFileOutcome,
    failure_reason: str | None = None,
    raw_extracted_text: str | None = None,
    bank_statement_id=None,
    transactions_extracted_count: int | None = None,
) -> IngestionRunFile:
    row = IngestionRunFile(
        ingestion_run_id=run.id,
        drive_file_id=drive_file_id,
        drive_file_name=drive_file_name,
        outcome=outcome,
        failure_reason=failure_reason,
        raw_extracted_text=raw_extracted_text,
        bank_statement_id=bank_statement_id,
        transactions_extracted_count=transactions_extracted_count,
    )
    db.add(row)
    db.flush()
    return row


def find_queued_recategorize_job(db: Session) -> RecategorizationJob | None:
    return db.scalar(select(RecategorizationJob).where(RecategorizationJob.status == RecategorizationJobStatus.QUEUED))


def claim_recategorize_job(db: Session, job: RecategorizationJob) -> None:
    job.status = RecategorizationJobStatus.RUNNING
    db.flush()


def complete_recategorize_job(db: Session, job: RecategorizationJob, updated_count: int) -> None:
    from datetime import datetime

    job.status = RecategorizationJobStatus.COMPLETED
    job.completed_at = datetime.now(UTC)
    job.updated_transaction_count = updated_count
    db.flush()


def fail_recategorize_job(db: Session, job: RecategorizationJob) -> None:
    from datetime import datetime

    job.status = RecategorizationJobStatus.FAILED
    job.completed_at = datetime.now(UTC)
    db.flush()
