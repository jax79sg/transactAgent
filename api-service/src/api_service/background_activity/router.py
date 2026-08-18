from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.background_activity import service
from api_service.background_activity.schemas import ActivitySummaryResponse
from api_service.db import get_db

router = APIRouter(prefix="/background-activity", tags=["background-activity"], dependencies=[Depends(get_current_user_id)])


@router.get("/summary", response_model=ActivitySummaryResponse)
def get_activity_summary(db: Session = Depends(get_db)) -> ActivitySummaryResponse:
    return service.get_activity_summary(db)
