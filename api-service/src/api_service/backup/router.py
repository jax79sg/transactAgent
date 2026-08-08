from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.backup import service
from api_service.backup.schemas import BackupStatusResponse
from api_service.db import get_db

router = APIRouter(prefix="/backups", tags=["backups"], dependencies=[Depends(get_current_user_id)])


@router.get("/status", response_model=BackupStatusResponse)
def get_backup_status(db: Session = Depends(get_db)) -> BackupStatusResponse:
    return service.get_latest_backup_status(db)
