"""Recurring Payments business logic (business-logic-model.md — Recurring
Payments Component). Implements AR-15..20.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.orm import Session
from transactagent_db.models import (
    Category,
    DetectionSuggestion,
    DetectionSuggestionStatus,
    EmbeddingStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
)

from api_service.config import settings
from api_service.errors import (
    CategoryNotFoundError,
    DetectionSuggestionNotNewError,
    InvalidRecurringPaymentError,
    MatchNotPendingError,
    NotFoundError,
)
from api_service.recurring_payments import cycle, repository
from api_service.recurring_payments.schemas import (
    AddFromDetectionSuggestionRequest,
    BulkImportRequest,
    BulkImportResponse,
    BulkImportRowFailure,
    DetectionSuggestionDTO,
    RecurringPaymentCreateRequest,
    RecurringPaymentDTO,
    RecurringPaymentMatchDTO,
    RecurringPaymentRef,
    RecurringPaymentsStatusSummaryDTO,
    RecurringPaymentUpdateRequest,
)
from api_service.transactions.schemas import CategoryRef, TransactionDTO


def _validate_frequency_shape(frequency_raw: str, due_month: int | None, due_day: int) -> RecurringPaymentFrequency:
    try:
        frequency = RecurringPaymentFrequency(frequency_raw)
    except ValueError:
        raise InvalidRecurringPaymentError(f"Unrecognized frequency '{frequency_raw}' -- must be monthly or annual") from None

    if frequency == RecurringPaymentFrequency.ANNUAL and due_month is None:
        raise InvalidRecurringPaymentError("An annual recurring payment requires dueMonth")  # BR-19
    if frequency == RecurringPaymentFrequency.MONTHLY and due_month is not None:
        raise InvalidRecurringPaymentError("A monthly recurring payment must not have dueMonth set")  # BR-19
    if not (1 <= due_day <= 31):
        raise InvalidRecurringPaymentError("dueDay must be between 1 and 31")  # BR-20
    if frequency == RecurringPaymentFrequency.ANNUAL and not (1 <= due_month <= 12):
        raise InvalidRecurringPaymentError("dueMonth must be between 1 and 12")

    return frequency


def _resolve_category(db: Session, category_id: UUID | None) -> Category | None:
    if category_id is None:
        return None
    category = repository.find_category(db, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    return category


def _to_category_ref(category: Category | None) -> CategoryRef | None:
    return CategoryRef(id=category.id, name=category.name) if category is not None else None


def _compute_status_and_set_aside(db: Session, payment: RecurringPayment, today: date) -> tuple[str, Decimal | None]:
    """AR-15/AR-16."""
    current_instance = cycle.latest_instance_on_or_before(payment.frequency, payment.due_month, payment.due_day, today)
    current_cycle_period = cycle.cycle_period_for(payment.frequency, current_instance)
    match = repository.find_match_for_cycle(db, payment.id, current_cycle_period)

    if match is not None and match.status == RecurringPaymentMatchStatus.PENDING:
        status_str = "pending_review"
    elif match is not None:  # approved or auto_applied
        next_instance = cycle.next_instance_after(payment.frequency, payment.due_month, payment.due_day, current_instance)
        if (next_instance - today).days <= settings.recurring_payment_due_soon_lead_days:
            status_str = "due_soon"
        else:
            status_str = "paid"
    elif current_instance < today:
        status_str = "overdue"
    else:
        status_str = "due_soon"  # due today, not yet overdue (FR-9's one-day grace)

    monthly_set_aside = (
        (payment.expected_amount / Decimal(12)) if payment.frequency == RecurringPaymentFrequency.ANNUAL else None
    )
    return status_str, monthly_set_aside


def _to_payment_dto(db: Session, payment: RecurringPayment, today: date) -> RecurringPaymentDTO:
    status_str, monthly_set_aside = _compute_status_and_set_aside(db, payment, today)
    return RecurringPaymentDTO(
        id=payment.id,
        name=payment.name,
        expected_amount=payment.expected_amount,
        frequency=payment.frequency.value,
        due_month=payment.due_month,
        due_day=payment.due_day,
        category=_to_category_ref(payment.category),
        is_trusted=payment.is_trusted,
        status=status_str,
        monthly_set_aside=monthly_set_aside,
    )


def list_recurring_payments(db: Session) -> list[RecurringPaymentDTO]:
    today = date.today()
    return [_to_payment_dto(db, p, today) for p in repository.list_recurring_payments(db)]


def _get_or_404(db: Session, payment_id: UUID) -> RecurringPayment:
    payment = repository.get_recurring_payment(db, payment_id)
    if payment is None:
        raise NotFoundError(f"Recurring payment {payment_id} not found")
    return payment


def get_recurring_payment(db: Session, payment_id: UUID) -> RecurringPaymentDTO:
    return _to_payment_dto(db, _get_or_404(db, payment_id), date.today())


def create_recurring_payment(db: Session, request: RecurringPaymentCreateRequest) -> RecurringPaymentDTO:
    frequency = _validate_frequency_shape(request.frequency, request.due_month, request.due_day)
    _resolve_category(db, request.category_id)
    payment = repository.create_recurring_payment(
        db,
        name=request.name,
        expected_amount=request.expected_amount,
        frequency=frequency,
        due_month=request.due_month,
        due_day=request.due_day,
        category_id=request.category_id,
    )
    return _to_payment_dto(db, payment, date.today())


def update_recurring_payment(db: Session, payment_id: UUID, request: RecurringPaymentUpdateRequest) -> RecurringPaymentDTO:
    payment = _get_or_404(db, payment_id)
    frequency = _validate_frequency_shape(request.frequency, request.due_month, request.due_day)
    _resolve_category(db, request.category_id)
    fields = {
        "name": request.name,
        "expected_amount": request.expected_amount,
        "frequency": frequency,
        "due_month": request.due_month,
        "due_day": request.due_day,
        "category_id": request.category_id,
    }
    # AR-22 (Epic 9): a name change invalidates whatever embedding is currently
    # stored (or pending) for this payment -- reset so the Ingestion Worker's
    # Embedding Manager re-embeds the new text. Any other field change leaves
    # embedding_status untouched.
    if payment.name != request.name:
        fields["embedding_status"] = EmbeddingStatus.PENDING
    repository.update_recurring_payment(db, payment, **fields)
    return _to_payment_dto(db, payment, date.today())


def delete_recurring_payment(db: Session, payment_id: UUID) -> None:
    payment = _get_or_404(db, payment_id)
    repository.delete_recurring_payment(db, payment)


def _parse_bulk_row_amount(amount_raw: str) -> Decimal:
    try:
        return Decimal(amount_raw)
    except InvalidOperation:
        raise InvalidRecurringPaymentError(f"'{amount_raw}' is not a valid amount") from None


def _parse_bulk_row_int(label: str, value_raw: str | None) -> int | None:
    if value_raw is None or value_raw == "":
        return None
    try:
        return int(value_raw)
    except ValueError:
        raise InvalidRecurringPaymentError(f"'{value_raw}' is not a valid {label}") from None


def bulk_import_recurring_payments(db: Session, request: BulkImportRequest) -> BulkImportResponse:
    """AR-19: every row is validated independently; a bad row never blocks the rest.

    BulkImportRow's amount/due_month/due_day are raw strings precisely so that an
    unparseable value surfaces as a per-row failure here, not as a FastAPI request-body
    422 that would reject every row in the batch before this loop ever runs."""
    created: list[RecurringPaymentDTO] = []
    failed: list[BulkImportRowFailure] = []

    for index, row in enumerate(request.rows):
        try:
            amount = _parse_bulk_row_amount(row.amount)
            due_month = _parse_bulk_row_int("dueMonth", row.due_month)
            due_day = _parse_bulk_row_int("dueDay", row.due_day)
            if due_day is None:
                raise InvalidRecurringPaymentError("dueDay is required")
            frequency = _validate_frequency_shape(row.frequency, due_month, due_day)
            payment = repository.create_recurring_payment(
                db,
                name=row.name,
                expected_amount=amount,
                frequency=frequency,
                due_month=due_month,
                due_day=due_day,
                category_id=None,
            )
            created.append(_to_payment_dto(db, payment, date.today()))
        except InvalidRecurringPaymentError as exc:
            failed.append(BulkImportRowFailure(row=index, reason=exc.message))

    return BulkImportResponse(created=created, failed=failed)


def _to_match_dto(match: RecurringPaymentMatch) -> RecurringPaymentMatchDTO:
    txn = match.transaction
    return RecurringPaymentMatchDTO(
        id=match.id,
        recurring_payment=RecurringPaymentRef(id=match.recurring_payment.id, name=match.recurring_payment.name),
        transaction=TransactionDTO(
            id=txn.id,
            transaction_date=txn.transaction_date,
            description=txn.description,
            out_flow=txn.out_flow,
            in_flow=txn.in_flow,
            currency=txn.currency,
            bank_name=txn.bank_name,
            category=CategoryRef(id=txn.category.id, name=txn.category.name),
            category_source=txn.category_source.value,
            converted_amount_sgd=txn.converted_amount_sgd,
            conversion_is_approximate=txn.conversion_is_approximate,
            conversion_unavailable=txn.conversion_unavailable,
            bank_statement_id=txn.bank_statement_id,
            embedding_status=txn.embedding_status.value,
        ),
        cycle_period=match.cycle_period,
        status=match.status.value,
        amount_at_match=match.amount_at_match,
        created_at=match.created_at,
    )


def list_pending_matches(db: Session) -> list[RecurringPaymentMatchDTO]:
    return [_to_match_dto(m) for m in repository.list_pending_matches(db)]


def _get_pending_match(db: Session, match_id: UUID) -> RecurringPaymentMatch:
    match = repository.find_match_by_id(db, match_id)
    if match is None:
        raise NotFoundError(f"Recurring payment match {match_id} not found")
    if match.status != RecurringPaymentMatchStatus.PENDING:
        raise MatchNotPendingError(f"Recurring payment match {match_id} is not pending (status={match.status.value})")
    return match


def approve_match(db: Session, match_id: UUID) -> RecurringPaymentMatchDTO:
    match = _get_pending_match(db, match_id)
    repository.resolve_match(db, match, RecurringPaymentMatchStatus.APPROVED)
    repository.set_trusted(db, match.recurring_payment)  # FR-7: first approval unlocks future auto-apply
    return _to_match_dto(match)


def reject_match(db: Session, match_id: UUID) -> RecurringPaymentMatchDTO:
    match = _get_pending_match(db, match_id)
    repository.resolve_match(db, match, RecurringPaymentMatchStatus.REJECTED)  # FR-8: no other side effect
    return _to_match_dto(match)


def _to_suggestion_dto(suggestion: DetectionSuggestion) -> DetectionSuggestionDTO:
    return DetectionSuggestionDTO(
        id=suggestion.id,
        description_pattern=suggestion.description_pattern,
        suggested_amount=suggestion.suggested_amount,
        suggested_category=_to_category_ref(suggestion.suggested_category),
        occurrence_count=suggestion.occurrence_count,
        status=suggestion.status.value,
    )


def list_detection_suggestions(db: Session) -> list[DetectionSuggestionDTO]:
    return [_to_suggestion_dto(s) for s in repository.list_detection_suggestions(db)]


def _get_new_suggestion(db: Session, suggestion_id: UUID) -> DetectionSuggestion:
    suggestion = repository.find_detection_suggestion(db, suggestion_id)
    if suggestion is None:
        raise NotFoundError(f"Detection suggestion {suggestion_id} not found")
    if suggestion.status != DetectionSuggestionStatus.NEW:
        raise DetectionSuggestionNotNewError(
            f"Detection suggestion {suggestion_id} is not new (status={suggestion.status.value})"
        )
    return suggestion


def dismiss_detection_suggestion(db: Session, suggestion_id: UUID) -> None:
    suggestion = _get_new_suggestion(db, suggestion_id)
    repository.resolve_detection_suggestion(db, suggestion, DetectionSuggestionStatus.DISMISSED)  # permanent, BR-22


def add_from_detection_suggestion(
    db: Session, suggestion_id: UUID, overrides: AddFromDetectionSuggestionRequest
) -> RecurringPaymentDTO:
    suggestion = _get_new_suggestion(db, suggestion_id)

    name = overrides.name or suggestion.description_pattern
    expected_amount = overrides.expected_amount if overrides.expected_amount is not None else suggestion.suggested_amount
    frequency_raw = overrides.frequency or "monthly"  # FR-12: detection is monthly-cadence only
    due_month = overrides.due_month
    due_day = overrides.due_day if overrides.due_day is not None else date.today().day
    category_id = overrides.category_id if overrides.category_id is not None else suggestion.suggested_category_id

    frequency = _validate_frequency_shape(frequency_raw, due_month, due_day)
    _resolve_category(db, category_id)
    payment = repository.create_recurring_payment(
        db,
        name=name,
        expected_amount=expected_amount,
        frequency=frequency,
        due_month=due_month,
        due_day=due_day,
        category_id=category_id,
    )
    repository.resolve_detection_suggestion(db, suggestion, DetectionSuggestionStatus.ADDED)
    return _to_payment_dto(db, payment, date.today())


def get_status_summary(db: Session) -> RecurringPaymentsStatusSummaryDTO:
    today = date.today()
    payments = repository.list_recurring_payments(db)
    due_soon = overdue = 0
    for payment in payments:
        status_str, _ = _compute_status_and_set_aside(db, payment, today)
        if status_str == "due_soon":
            due_soon += 1
        elif status_str == "overdue":
            overdue += 1

    return RecurringPaymentsStatusSummaryDTO(
        due_soon_count=due_soon,
        overdue_count=overdue,
        pending_match_count=repository.count_pending_matches(db),
        new_suggestion_count=repository.count_new_detection_suggestions(db),
    )
