"""Balance endpoints (Epic 13, `domain-entities.md`): read-only. Every request needs the same login as the rest of the
API (NFR-AB-6). The static paths are declared before anything parameterised could shadow them."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.balances import service
from api_service.balances.calculation import AUTO
from api_service.balances.schemas import (
    BalancesResponse,
    DiscrepanciesResponse,
    SeriesResponse,
)
from api_service.db import get_db

router = APIRouter(prefix="/balances", tags=["balances"], dependencies=[Depends(get_current_user_id)])


@router.get("/series", response_model=SeriesResponse)
def get_series(
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    granularity: str = Query(default=AUTO),
    db: Session = Depends(get_db),
) -> SeriesResponse:
    return service.get_series(db, start=start, end=end, granularity=granularity)


@router.get("/discrepancies", response_model=DiscrepanciesResponse)
def get_discrepancies(db: Session = Depends(get_db)) -> DiscrepanciesResponse:
    return service.get_discrepancies(db)


@router.get("", response_model=BalancesResponse)
def get_balances(
    on_date: date | None = Query(default=None, alias="date"),
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BalancesResponse:
    return service.get_balances(db, on_date=on_date, month=month)
