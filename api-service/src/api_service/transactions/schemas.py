from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from api_service.schemas import CamelModel

FlowDirection = Literal["in", "out"]
CategorySourceFilter = Literal["similarity", "llm", "manual", "unsure"]
GroupByOption = Literal["category", "bank", "month", "categorySource"]
SortByOption = Literal["date", "amount", "category", "bank"]
SortDir = Literal["asc", "desc"]


class TransactionFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    bank: str | None = None
    category: str | None = None  # category name, "UNSURE" shortcut supported (US-3.5)
    flow_direction: FlowDirection | None = None
    currency: str | None = None
    text_search: str | None = None
    category_source: CategorySourceFilter | None = None
    group_by: GroupByOption | None = None
    sort_by: SortByOption = "date"
    sort_dir: SortDir = "desc"


class TransactionListQuery(TransactionFilter):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1)


class CategoryRef(CamelModel):
    id: UUID
    name: str


class TransactionDTO(CamelModel):
    id: UUID
    transaction_date: date
    description: str
    out_flow: Decimal | None
    in_flow: Decimal | None
    currency: str
    bank_name: str
    category: CategoryRef
    category_source: str
    converted_amount_sgd: Decimal | None
    conversion_is_approximate: bool
    conversion_unavailable: bool
    bank_statement_id: UUID


class GroupSummary(CamelModel):
    group_key: str
    group_label: str
    subtotal_out_flow_sgd: Decimal
    subtotal_in_flow_sgd: Decimal
    transaction_count: int


class TransactionPage(CamelModel):
    items: list[TransactionDTO]
    page: int
    page_size: int
    total_count: int
    groups: list[GroupSummary] | None = None


class CategoryCorrectionRequest(CamelModel):
    category_id: UUID


class TransactionUpdatedResponse(CamelModel):
    transaction: TransactionDTO
    recategorization_job_id: UUID
