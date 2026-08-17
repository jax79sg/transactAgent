"""Backup Manager Component (Epic 7, business-logic-model.md). Checked as the
poll loop's lowest-priority, third branch -- only when no ingestion run or
recategorization job was found that cycle (services.md addendum)."""

import csv
import io
import logging
from datetime import UTC, date, datetime

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    BackupRunFailureCategory,
    BackupRunOutcome,
    Transaction,
)

from ingestion_worker.backup import repository as backup_repository
from ingestion_worker.clients import drive_client
from ingestion_worker.clients.drive_client import (
    DriveFileRef,
    DriveNotConnectedError,
    DriveReauthRequiredError,
)
from ingestion_worker.clients.retry import TransientError
from ingestion_worker.config import settings

logger = logging.getLogger(__name__)

# WR-14: retention only ever considers files matching this convention -- a file
# that doesn't match (e.g. something a user manually placed in the folder) is
# never a deletion candidate, no matter how old it is.
_BACKUP_FILENAME_PREFIX = "transactions-backup-"
_BACKUP_FILENAME_SUFFIX = ".csv"

# WR-13: full column-for-column snapshot, in Transaction model declaration order.
_TRANSACTION_COLUMNS = [
    "id",
    "bank_statement_id",
    "transaction_date",
    "description",
    "out_flow",
    "in_flow",
    "currency",
    "bank_name",
    "category_id",
    "category_source",
    "converted_amount_sgd",
    "conversion_is_approximate",
    "conversion_unavailable",
    "fx_rate_used_id",
    "created_at",
    "updated_at",
]

_DRIVE_CONNECTIVITY_ERRORS = (DriveNotConnectedError, DriveReauthRequiredError, TransientError, HttpError)


def is_backup_due_now(db: Session) -> bool:
    """WR-11: due when both the schedule time has passed AND no attempt (success
    or failure) has been recorded yet for today. Checked unconditionally on every
    poll cycle -- this same check is what makes FR-8 catch-up work with no
    separate startup code path (see functional-design-plan.md)."""
    now = datetime.now()
    if now.hour < settings.backup_schedule_hour:
        return False
    return backup_repository.find_backup_run_for_date(db, now.date()) is None


def run_backup(db: Session) -> None:
    """WR-12: MUST catch every exception and MUST always write exactly one
    BackupRun row before returning -- an escaped exception would leave
    is_backup_due_now() returning True on every subsequent poll cycle for the
    rest of the day, a silent retry storm that breaks FR-9's no-same-night-retry
    rule."""
    backup_date = date.today()
    started_at = datetime.now(UTC)
    try:
        transactions = list(db.scalars(select(Transaction)))
        csv_bytes = _build_csv(transactions)
        folder_id = drive_client.ensure_backup_folder_exists(db, settings.google_drive_backup_folder_id)
        filename = f"{_BACKUP_FILENAME_PREFIX}{started_at.strftime('%Y%m%dT%H%M%SZ')}{_BACKUP_FILENAME_SUFFIX}"
        drive_client.upload_file(db, folder_id, filename, csv_bytes, "text/csv")
        _enforce_retention(db, folder_id)
        backup_repository.record_backup_run(
            db,
            backup_date=backup_date,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            outcome=BackupRunOutcome.SUCCESS,
            transaction_count=len(transactions),
            backup_filename=filename,
        )
        logger.info("Backup %s: uploaded %s (%d transaction(s))", backup_date, filename, len(transactions))
    except _DRIVE_CONNECTIVITY_ERRORS as exc:
        logger.warning("Backup %s failed (Drive connectivity): %s", backup_date, exc)
        backup_repository.record_backup_run(
            db,
            backup_date=backup_date,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.DRIVE_CONNECTIVITY,
        )
    except Exception:
        logger.exception("Backup %s failed unexpectedly", backup_date)
        backup_repository.record_backup_run(
            db,
            backup_date=backup_date,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.OTHER,
        )


def _build_csv(transactions: list[Transaction]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_TRANSACTION_COLUMNS)
    for txn in transactions:
        writer.writerow([_serialize(getattr(txn, column)) for column in _TRANSACTION_COLUMNS])
    return buffer.getvalue().encode("utf-8")


def _serialize(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):  # enum columns (category_source)
        return value.value
    return str(value)


def _enforce_retention(db: Session, folder_id: str) -> None:
    files = drive_client.list_backup_folder_files(db, folder_id)
    candidates: list[DriveFileRef] = sorted(
        (f for f in files if f.name.startswith(_BACKUP_FILENAME_PREFIX) and f.name.endswith(_BACKUP_FILENAME_SUFFIX)),
        key=lambda f: f.created_time or "",
        reverse=True,
    )
    for stale in candidates[settings.backup_retention_count :]:
        drive_client.delete_file(db, stale)
