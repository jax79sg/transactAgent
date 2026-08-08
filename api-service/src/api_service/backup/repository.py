from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import BackupRun


def get_latest_backup_run(db: Session) -> BackupRun | None:
    """AR-14: the most recent attempt by backup_date -- None if the Ingestion
    Worker's Backup Manager hasn't written a row yet (no backup has run)."""
    return db.scalar(select(BackupRun).order_by(BackupRun.backup_date.desc()).limit(1))
