from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.dashboards import service
from api_service.dashboards.schemas import (
    BankBreakdownPoint,
    BankBreakdownResponse,
    CashFlowPoint,
    CashFlowResponse,
    CategoryTrendPoint,
    CategoryTrendResponse,
    ConversionDisclosure,
    DashboardFilter,
)
from api_service.db import get_db

router = APIRouter(prefix="/dashboards", tags=["dashboards"], dependencies=[Depends(get_current_user_id)])


@router.get("/category-trends", response_model=CategoryTrendResponse)
def category_trends(filters: DashboardFilter = Depends(), db: Session = Depends(get_db)) -> CategoryTrendResponse:
    series, disclosure = service.get_category_trends(db, filters)
    return CategoryTrendResponse(
        series=[CategoryTrendPoint(**p) for p in series],
        disclosure=ConversionDisclosure(**disclosure),
    )


@router.get("/cash-flow", response_model=CashFlowResponse)
def cash_flow(filters: DashboardFilter = Depends(), db: Session = Depends(get_db)) -> CashFlowResponse:
    series, disclosure = service.get_cash_flow(db, filters)
    return CashFlowResponse(
        series=[CashFlowPoint(**p) for p in series],
        disclosure=ConversionDisclosure(**disclosure),
    )


@router.get("/bank-breakdown", response_model=BankBreakdownResponse)
def bank_breakdown(filters: DashboardFilter = Depends(), db: Session = Depends(get_db)) -> BankBreakdownResponse:
    series, disclosure = service.get_bank_breakdown(db, filters)
    return BankBreakdownResponse(
        series=[BankBreakdownPoint(**p) for p in series],
        disclosure=ConversionDisclosure(**disclosure),
    )
