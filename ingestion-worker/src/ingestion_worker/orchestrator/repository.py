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
    from datetime import datetime, timezone

    run.status = (
        IngestionRunStatus.COMPLETED_WITH_FAILURES if run.files_failed_count > 0 else IngestionRunStatus.COMPLETED
    )
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


def fail_run(db: Session, run: IngestionRun) -> None:
    from datetime import datetime, timezone

    run.status = IngestionRunStatus.FAILED
    run.completed_at = datetime.now(timezone.utc)
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
    from datetime import datetime, timezone

    job.status = RecategorizationJobStatus.COMPLETED
    job.completed_at = datetime.now(timezone.utc)
    job.updated_transaction_count = updated_count
    db.flush()


def fail_recategorize_job(db: Session, job: RecategorizationJob) -> None:
    from datetime import datetime, timezone

    job.status = RecategorizationJobStatus.FAILED
    job.completed_at = datetime.now(timezone.utc)
    db.flush()
