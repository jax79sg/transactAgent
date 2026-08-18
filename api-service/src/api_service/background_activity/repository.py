from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    IngestionRun,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
)


def get_current_activity(db: Session) -> tuple[str, datetime] | None:
    """AR-35: at most one 'current' job is ever reported. Reads both tables' running
    rows defensively (the single-active-job invariant lives in the worker's poll loop,
    not a cross-table DB constraint) and prefers the more recently started one."""
    candidates: list[tuple[str, datetime]] = []

    run = db.scalar(select(IngestionRun).where(IngestionRun.status == IngestionRunStatus.RUNNING))
    if run is not None:
        candidates.append(("ingestion_run", run.started_at))

    job = db.scalar(select(RecategorizationJob).where(RecategorizationJob.status == RecategorizationJobStatus.RUNNING))
    if job is not None:
        candidates.append(("recategorization_job", job.created_at))

    if not candidates:
        return None
    return max(candidates, key=lambda c: c[1])


def get_recent_activity(db: Session, limit: int = 10) -> list[tuple[str, datetime]]:
    """AR-36/AR-37: combine-then-sort-then-limit across both tables. Each table is
    independently capped at `limit` before merging, which is sufficient to guarantee
    the true top `limit` overall is present in the merged set."""
    runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.completed_at.is_not(None))
        .order_by(IngestionRun.completed_at.desc())
        .limit(limit)
    ).all()
    jobs = db.scalars(
        select(RecategorizationJob)
        .where(RecategorizationJob.completed_at.is_not(None))
        .order_by(RecategorizationJob.completed_at.desc())
        .limit(limit)
    ).all()

    combined = [("ingestion_run", r.completed_at) for r in runs] + [
        ("recategorization_job", j.completed_at) for j in jobs
    ]
    combined.sort(key=lambda c: c[1], reverse=True)
    return combined[:limit]
