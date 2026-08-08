from datetime import datetime

from api_service.schemas import CamelModel


class BackupStatusResponse(CamelModel):
    last_run_at: datetime | None
    outcome: str | None  # 'success' | 'failed' | null (AR-14: null means no backup has run yet)
    failure_category: str | None  # 'drive_connectivity' | 'other' | null
    transaction_count: int | None
    backup_filename: str | None
