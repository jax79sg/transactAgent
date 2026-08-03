from datetime import datetime
from uuid import UUID

from api_service.schemas import CamelModel


class StartRunResponse(CamelModel):
    run_id: UUID


class RunStatusResponse(CamelModel):
    run_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    files_found_count: int
    files_processed_count: int
    files_skipped_count: int
    files_failed_count: int


class RunHistoryPage(CamelModel):
    items: list[RunStatusResponse]
    page: int
    page_size: int
    total_count: int


class RunFileDetail(CamelModel):
    id: UUID
    drive_file_name: str
    outcome: str
    failure_reason: str | None
    transactions_extracted_count: int | None
    processed_at: datetime


class RunLogLine(CamelModel):
    id: int
    logged_at: datetime
    level: str
    logger_name: str
    message: str
