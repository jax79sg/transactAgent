from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from api_service.schemas import CamelModel


class DashboardFilter(BaseModel):
    date_from: date
    date_to: date
    currency: str | None = None


class ConversionDisclosure(CamelModel):
    approximate_count: int
    excluded_count: int
    excluded_transaction_ids: list[UUID]


class CategoryTrendPoint(CamelModel):
    category: str
    month: str  # YYYY-MM
    total_sgd: Decimal


class CategoryTrendResponse(CamelModel):
    series: list[CategoryTrendPoint]
    disclosure: ConversionDisclosure


class CashFlowPoint(CamelModel):
    month: str
    income_sgd: Decimal
    expense_sgd: Decimal
    net_sgd: Decimal


class CashFlowResponse(CamelModel):
    series: list[CashFlowPoint]
    disclosure: ConversionDisclosure


class BankBreakdownPoint(CamelModel):
    bank_name: str
    month: str
    total_sgd: Decimal


class BankBreakdownResponse(CamelModel):
    series: list[BankBreakdownPoint]
    disclosure: ConversionDisclosure
