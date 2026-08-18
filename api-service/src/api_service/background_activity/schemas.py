from datetime import datetime

from api_service.schemas import CamelModel


class CurrentActivity(CamelModel):
    job_type: str  # 'ingestion_run' | 'recategorization_job'
    started_at: datetime


class RecentActivityEntry(CamelModel):
    job_type: str  # 'ingestion_run' | 'recategorization_job'
    completed_at: datetime


class ActivitySummaryResponse(CamelModel):
    current: CurrentActivity | None
    recent: list[RecentActivityEntry]
