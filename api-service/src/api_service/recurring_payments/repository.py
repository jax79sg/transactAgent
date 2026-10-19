from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from transactagent_db.models import (
    Category,
    DetectionSuggestion,
    DetectionSuggestionStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    Transaction,
)

_MATCH_EAGER_LOAD = (
    joinedload(RecurringPaymentMatch.recurring_payment),
    joinedload(RecurringPaymentMatch.transaction).joinedload(Transaction.category),
)

_LIVE_OR_PENDING_STATUSES = (
    RecurringPaymentMatchStatus.PENDING,
    RecurringPaymentMatchStatus.APPROVED,
    RecurringPaymentMatchStatus.AUTO_APPLIED,
)


def list_recurring_payments(db: Session) -> list[RecurringPayment]:
    return list(db.scalars(select(RecurringPayment).options(joinedload(RecurringPayment.category))))


def get_recurring_payment(db: Session, payment_id: UUID) -> RecurringPayment | None:
    return db.get(RecurringPayment, payment_id, options=[joinedload(RecurringPayment.category)])


def create_recurring_payment(
    db: Session,
    *,
    name: str,
    expected_amount: Decimal,
    frequency: RecurringPaymentFrequency,
    due_month: int | None,
    due_day: int,
    category_id: UUID | None,
    due_soon_lead_days: int | None = None,
) -> RecurringPayment:
    payment = RecurringPayment(
        name=name,
        expected_amount=expected_amount,
        frequency=frequency,
        due_month=due_month,
        due_day=due_day,
        category_id=category_id,
        due_soon_lead_days=due_soon_lead_days,
    )
    db.add(payment)
    db.flush()
    return payment


def update_recurring_payment(db: Session, payment: RecurringPayment, **fields) -> RecurringPayment:
    for key, value in fields.items():
        setattr(payment, key, value)
    db.flush()
    return payment


def delete_recurring_payment(db: Session, payment: RecurringPayment) -> None:
    db.delete(payment)
    db.flush()


def find_category(db: Session, category_id: UUID) -> Category | None:
    return db.get(Category, category_id)


def find_match_for_cycle(db: Session, recurring_payment_id: UUID, cycle_period: str) -> RecurringPaymentMatch | None:
    """AR-15: the single query behind status computation -- returns the live/pending
    match for this cycle if one exists, regardless of which of the 3 non-rejected
    statuses it's in (the caller distinguishes paid vs. pending_review)."""
    stmt = select(RecurringPaymentMatch).where(
        RecurringPaymentMatch.recurring_payment_id == recurring_payment_id,
        RecurringPaymentMatch.cycle_period == cycle_period,
        RecurringPaymentMatch.status.in_(_LIVE_OR_PENDING_STATUSES),
    )
    return db.scalar(stmt)


def count_pending_matches(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(RecurringPaymentMatch)
            .where(RecurringPaymentMatch.status == RecurringPaymentMatchStatus.PENDING)
        )
        or 0
    )


def count_new_detection_suggestions(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(DetectionSuggestion)
            .where(DetectionSuggestion.status == DetectionSuggestionStatus.NEW)
        )
        or 0
    )


def list_pending_matches(db: Session) -> list[RecurringPaymentMatch]:
    stmt = (
        select(RecurringPaymentMatch)
        .where(RecurringPaymentMatch.status == RecurringPaymentMatchStatus.PENDING)
        .options(*_MATCH_EAGER_LOAD)
        .order_by(RecurringPaymentMatch.created_at.desc())
    )
    return list(db.scalars(stmt))


def find_match_by_id(db: Session, match_id: UUID) -> RecurringPaymentMatch | None:
    return db.get(RecurringPaymentMatch, match_id, options=list(_MATCH_EAGER_LOAD))


def resolve_match(db: Session, match: RecurringPaymentMatch, status: RecurringPaymentMatchStatus) -> None:
    match.status = status
    match.resolved_at = datetime.now(UTC)
    db.flush()


def set_trusted(db: Session, payment: RecurringPayment) -> None:
    if not payment.is_trusted:
        payment.is_trusted = True
        db.flush()


def list_detection_suggestions(db: Session) -> list[DetectionSuggestion]:
    stmt = (
        select(DetectionSuggestion)
        .where(DetectionSuggestion.status == DetectionSuggestionStatus.NEW)
        .options(joinedload(DetectionSuggestion.suggested_category))
        .order_by(DetectionSuggestion.created_at.desc())
    )
    return list(db.scalars(stmt))


def find_detection_suggestion(db: Session, suggestion_id: UUID) -> DetectionSuggestion | None:
    return db.get(DetectionSuggestion, suggestion_id, options=[joinedload(DetectionSuggestion.suggested_category)])


def resolve_detection_suggestion(db: Session, suggestion: DetectionSuggestion, status: DetectionSuggestionStatus) -> None:
    suggestion.status = status
    suggestion.resolved_at = datetime.now(UTC)
    db.flush()
