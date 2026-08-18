"""Background Activity Component (business-logic-model.md). Read-only -- this
component has no write path at all; ingestion_runs/recategorization_jobs rows are
written exclusively by the Ingestion Worker Service.
"""

from sqlalchemy.orm import Session

from api_service.background_activity import repository
from api_service.background_activity.schemas import (
    ActivitySummaryResponse,
    CurrentActivity,
    RecentActivityEntry,
)


def get_activity_summary(db: Session) -> ActivitySummaryResponse:
    current = repository.get_current_activity(db)
    recent = repository.get_recent_activity(db)
    return ActivitySummaryResponse(
        current=CurrentActivity(job_type=current[0], started_at=current[1]) if current else None,
        recent=[RecentActivityEntry(job_type=job_type, completed_at=completed_at) for job_type, completed_at in recent],
    )
