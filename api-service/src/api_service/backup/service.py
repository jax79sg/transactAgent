"""Backup Status business logic (business-logic-model.md — Backup Status Component).
Implements AR-14. Read-only -- this component has no write path at all; BackupRun
rows are written exclusively by the Ingestion Worker Service's Backup Manager.
"""

from sqlalchemy.orm import Session

from api_service.backup import repository
from api_service.backup.schemas import BackupStatusResponse


def get_latest_backup_status(db: Session) -> BackupStatusResponse:
    run = repository.get_latest_backup_run(db)
    if run is None:
        return BackupStatusResponse(
            last_run_at=None, outcome=None, failure_category=None, transaction_count=None, backup_filename=None
        )
    return BackupStatusResponse(
        last_run_at=run.started_at,
        outcome=run.outcome.value,
        failure_category=run.failure_category.value if run.failure_category else None,
        transaction_count=run.transaction_count,
        backup_filename=run.backup_filename,
    )
