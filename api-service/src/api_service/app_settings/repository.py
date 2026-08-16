"""Query wrappers for SettingChange (Repository Layer, Configurable Application
Settings) and the AR-31 busy/idle read against existing Ingestion Worker state."""

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from transactagent_db.models import (
    IngestionRun,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
    SettingChange,
    SettingOwningService,
)


def insert_change(
    db: Session,
    *,
    setting_name: str,
    owning_service: SettingOwningService,
    previous_value: str | None,
    new_value: str,
) -> SettingChange:
    change = SettingChange(
        setting_name=setting_name,
        owning_service=owning_service,
        previous_value=previous_value,
        new_value=new_value,
    )
    db.add(change)
    db.flush()
    return change


def list_changes(db: Session) -> list[SettingChange]:
    return list(db.scalars(select(SettingChange).order_by(SettingChange.changed_at.desc())))


def is_ingestion_worker_busy(db: Session) -> bool:
    """AR-31: a plain, point-in-time read -- any IngestionRun or RecategorizationJob
    currently 'running' means the worker is mid-cycle on something that shouldn't be
    interrupted by a restart. No new table (Key Design Resolution 2, Application
    Design)."""
    running_run = exists().where(IngestionRun.status == IngestionRunStatus.RUNNING)
    running_job = exists().where(RecategorizationJob.status == RecategorizationJobStatus.RUNNING)
    return bool(db.scalar(select(or_(running_run, running_job))))
