from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.costs import service
from api_service.costs.schemas import CostsFilter, CostsResponse
from api_service.db import get_db

router = APIRouter(prefix="/costs", tags=["costs"], dependencies=[Depends(get_current_user_id)])


@router.get("", response_model=CostsResponse)
def get_costs(filters: CostsFilter = Depends(), db: Session = Depends(get_db)) -> CostsResponse:
    return service.get_costs(db, filters)
