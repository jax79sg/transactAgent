from datetime import datetime
from decimal import Decimal
from uuid import UUID

from api_service.schemas import CamelModel
from api_service.transactions.schemas import CategoryRef, TransactionDTO


class RecurringPaymentDTO(CamelModel):
    id: UUID
    name: str
    expected_amount: Decimal
    frequency: str  # "monthly" | "annual"
    due_month: int | None
    due_day: int
    category: CategoryRef | None
    is_trusted: bool
    status: str  # "due_soon" | "overdue" | "pending_review" | "paid" -- AR-15
    monthly_set_aside: Decimal | None  # AR-16, annual only


class RecurringPaymentCreateRequest(CamelModel):
    name: str
    expected_amount: Decimal
    frequency: str
    due_month: int | None = None
    due_day: int
    category_id: UUID | None = None


class RecurringPaymentUpdateRequest(CamelModel):
    name: str
    expected_amount: Decimal
    frequency: str
    due_month: int | None = None
    due_day: int
    category_id: UUID | None = None


class BulkImportRow(CamelModel):
    """Amount/due_month/due_day are raw strings, not Decimal/int -- a single
    unparseable value here must become a per-row failure (AR-19), not a
    whole-request 422 raised by FastAPI's own body validation before the
    per-row isolation logic in service.py ever runs."""

    name: str
    amount: str
    frequency: str
    due_month: str | None = None
    due_day: str | None = None


class BulkImportRequest(CamelModel):
    rows: list[BulkImportRow]


class BulkImportRowFailure(CamelModel):
    row: int
    reason: str


class BulkImportResponse(CamelModel):
    created: list[RecurringPaymentDTO]
    failed: list[BulkImportRowFailure]


class RecurringPaymentRef(CamelModel):
    id: UUID
    name: str


class RecurringPaymentMatchDTO(CamelModel):
    id: UUID
    recurring_payment: RecurringPaymentRef
    transaction: TransactionDTO
    cycle_period: str
    status: str
    amount_at_match: Decimal
    created_at: datetime


class DetectionSuggestionDTO(CamelModel):
    id: UUID
    description_pattern: str
    suggested_amount: Decimal
    suggested_category: CategoryRef | None
    occurrence_count: int
    status: str


class AddFromDetectionSuggestionRequest(CamelModel):
    name: str | None = None
    expected_amount: Decimal | None = None
    frequency: str | None = None
    due_month: int | None = None
    due_day: int | None = None
    category_id: UUID | None = None


class RecurringPaymentsStatusSummaryDTO(CamelModel):
    due_soon_count: int
    overdue_count: int
    pending_match_count: int
    new_suggestion_count: int
