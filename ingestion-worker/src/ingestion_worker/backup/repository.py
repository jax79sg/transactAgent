from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    BackupRun,
    BackupRunFailureCategory,
    BackupRunOutcome,
)


def find_backup_run_for_date(db: Session, backup_date: date) -> BackupRun | None:
    """BR-17/WR-11: the single source of truth for whether today's backup has
    already been attempted (success or failure both count)."""
    return db.scalar(select(BackupRun).where(BackupRun.backup_date == backup_date))


def record_backup_run(
    db: Session,
    *,
    backup_date: date,
    started_at: datetime,
    completed_at: datetime,
    outcome: BackupRunOutcome,
    failure_category: BackupRunFailureCategory | None = None,
    transaction_count: int | None = None,
    backup_filename: str | None = None,
) -> BackupRun:
    """WR-12: called exactly once per attempt, in run_backup()'s single write path
    (success or failure) -- never partially, never twice for the same backup_date
    (BR-17 enforces that at the DB level too)."""
    row = BackupRun(
        backup_date=backup_date,
        started_at=started_at,
        completed_at=completed_at,
        outcome=outcome,
        failure_category=failure_category,
        transaction_count=transaction_count,
        backup_filename=backup_filename,
    )
    db.add(row)
    db.flush()
    return row
