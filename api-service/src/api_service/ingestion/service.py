"""Ingestion trigger/status/history business logic (business-logic-model.md — Ingestion
Trigger & Status Component). Implements AR-6 (single active run).
"""

from uuid import UUID

from sqlalchemy.orm import Session
from transactagent_db.models import IngestionRun, IngestionRunStatus

from api_service.errors import (
    IngestionRunAlreadyActiveError,
    NotFoundError,
    RunNotCancellableError,
)
from api_service.ingestion import repository

_CANCELLABLE_STATUSES = (IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING)


def start_run(db: Session, triggered_by_user_id: UUID) -> IngestionRun:
    active_run = repository.find_active_run(db)
    if active_run is not None:
        raise IngestionRunAlreadyActiveError(
            "An ingestion run is already in progress",
            details={"existingRunId": str(active_run.id)},
        )
    return repository.create_queued_run(db, triggered_by_user_id=triggered_by_user_id)


def get_run_status(db: Session, run_id: UUID) -> IngestionRun:
    run = repository.find_by_id(db, run_id)
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    return run


def cancel_run(db: Session, run_id: UUID) -> IngestionRun:
    """Requests cancellation of a queued/running run -- doesn't cancel it directly
    (that would race with the worker, the sole writer of `status`); see
    repository.request_cancellation. Idempotent: cancelling an already
    cancel-requested run is a no-op, not an error."""
    run = repository.find_by_id(db, run_id)
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    if run.status not in _CANCELLABLE_STATUSES:
        raise RunNotCancellableError(
            f"Ingestion run {run_id} cannot be cancelled (status: {run.status.value})",
            details={"status": run.status.value},
        )
    repository.request_cancellation(db, run)
    return run


def list_run_history(db: Session, page: int, page_size: int) -> tuple[list[IngestionRun], int]:
    return repository.list_runs(db, page=page, page_size=page_size)


def list_run_files(db: Session, run_id: UUID):
    run = repository.find_by_id(db, run_id)
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    return repository.list_files_for_run(db, run_id)


_MAX_LOG_LINES_PER_POLL = 500


def list_run_logs(db: Session, run_id: UUID, after_id: int | None):
    run = repository.find_by_id(db, run_id)
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    return repository.list_logs_for_run(db, run_id, after_id=after_id, limit=_MAX_LOG_LINES_PER_POLL)
