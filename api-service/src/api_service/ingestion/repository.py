"""Query wrappers for IngestionRun / IngestionRunFile / IngestionRunLog (Repository Layer)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from transactagent_db.models import IngestionRun, IngestionRunFile, IngestionRunLog, IngestionRunStatus


def find_active_run(db: Session) -> IngestionRun | None:
    return db.scalar(
        select(IngestionRun).where(
            IngestionRun.status.in_([IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING])
        )
    )


def create_queued_run(db: Session, *, triggered_by_user_id: UUID) -> IngestionRun:
    run = IngestionRun(triggered_by_user_id=triggered_by_user_id, status=IngestionRunStatus.QUEUED)
    db.add(run)
    db.flush()
    return run


def find_by_id(db: Session, run_id: UUID) -> IngestionRun | None:
    return db.get(IngestionRun, run_id)


def request_cancellation(db: Session, run: IngestionRun) -> None:
    """Sets cancel_requested_at only -- never touches `status`. The worker (a
    separate process) is the sole writer of `status`; it checks this column
    between files (never mid-file) and transitions the run to CANCELLED itself.
    This split keeps the two processes from ever racing on the same column."""
    from datetime import datetime, timezone

    if run.cancel_requested_at is None:
        run.cancel_requested_at = datetime.now(timezone.utc)
        db.commit()


def list_runs(db: Session, page: int, page_size: int) -> tuple[list[IngestionRun], int]:
    total_count = db.scalar(select(func.count()).select_from(IngestionRun)) or 0
    stmt = (
        select(IngestionRun)
        .order_by(IngestionRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(stmt)), total_count


def list_files_for_run(db: Session, run_id: UUID) -> list[IngestionRunFile]:
    stmt = (
        select(IngestionRunFile)
        .where(IngestionRunFile.ingestion_run_id == run_id)
        .order_by(IngestionRunFile.processed_at)
    )
    return list(db.scalars(stmt))


def list_logs_for_run(db: Session, run_id: UUID, after_id: int | None, limit: int) -> list[IngestionRunLog]:
    """Live log-tail polling: returns lines strictly after `after_id` (the highest id
    the caller has already seen), ordered by id ascending -- the same monotonic id used
    as the incremental cursor."""
    stmt = select(IngestionRunLog).where(IngestionRunLog.ingestion_run_id == run_id)
    if after_id is not None:
        stmt = stmt.where(IngestionRunLog.id > after_id)
    stmt = stmt.order_by(IngestionRunLog.id).limit(limit)
    return list(db.scalars(stmt))
