from datetime import UTC
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    DetectionScanRun,
    DetectionSuggestion,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    Transaction,
)

_LIVE_MATCH_STATUSES = (
    RecurringPaymentMatchStatus.PENDING,
    RecurringPaymentMatchStatus.APPROVED,
    RecurringPaymentMatchStatus.AUTO_APPLIED,
)


def list_recurring_payments(db: Session) -> list[RecurringPayment]:
    return list(db.scalars(select(RecurringPayment)))


def has_live_match(db: Session, recurring_payment_id: UUID, cycle_period: str) -> bool:
    """BR-21's application-layer mirror -- checked before attempting an insert,
    not relied on alone (the partial unique index is the real guarantee)."""
    stmt = select(RecurringPaymentMatch.id).where(
        RecurringPaymentMatch.recurring_payment_id == recurring_payment_id,
        RecurringPaymentMatch.cycle_period == cycle_period,
        RecurringPaymentMatch.status.in_(_LIVE_MATCH_STATUSES),
    )
    return db.scalar(stmt) is not None


def record_match(
    db: Session,
    *,
    recurring_payment_id: UUID,
    transaction_id: UUID,
    cycle_period: str,
    status: RecurringPaymentMatchStatus,
    amount_at_match: Decimal,
) -> RecurringPaymentMatch:
    from datetime import datetime

    match = RecurringPaymentMatch(
        recurring_payment_id=recurring_payment_id,
        transaction_id=transaction_id,
        cycle_period=cycle_period,
        status=status,
        amount_at_match=amount_at_match,
        resolved_at=datetime.now(UTC) if status != RecurringPaymentMatchStatus.PENDING else None,
    )
    db.add(match)
    db.flush()
    return match


def list_all_transactions_for_detection(db: Session) -> list[Transaction]:
    """WR-19: the detection scan considers the full transaction history -- this
    project's data volume is personal-scale (thousands, not millions), same
    reasoning list_similarity_candidates already relies on for categorization."""
    return list(db.scalars(select(Transaction)))


def list_matched_transaction_ids(db: Session) -> set[UUID]:
    """Transactions already covered by any RecurringPaymentMatch (any status) --
    used by the detection scan to skip patterns already represented by an existing
    RecurringPayment, per WR-19."""
    return set(db.scalars(select(RecurringPaymentMatch.transaction_id)))


def find_suggestion_by_pattern(db: Session, description_pattern: str) -> DetectionSuggestion | None:
    """Pre-check mirroring BR-22 -- avoids attempting a doomed insert where
    practical, though the unique constraint is the real backstop (BR-22)."""
    return db.scalar(select(DetectionSuggestion).where(DetectionSuggestion.description_pattern == description_pattern))


def find_latest_detection_scan_run(db: Session) -> DetectionScanRun | None:
    return db.scalar(select(DetectionScanRun).order_by(DetectionScanRun.ran_at.desc()).limit(1))


def record_detection_scan_run(db: Session) -> DetectionScanRun:
    run = DetectionScanRun()
    db.add(run)
    db.flush()
    return run


def record_detection_suggestion(
    db: Session,
    *,
    description_pattern: str,
    suggested_amount: Decimal,
    suggested_category_id: UUID | None,
    occurrence_count: int,
    detected_frequency: RecurringPaymentFrequency | None = None,
    suggested_due_month: int | None = None,
    suggested_due_day: int | None = None,
) -> DetectionSuggestion:
    suggestion = DetectionSuggestion(
        description_pattern=description_pattern,
        suggested_amount=suggested_amount,
        suggested_category_id=suggested_category_id,
        occurrence_count=occurrence_count,
        detected_frequency=detected_frequency,
        suggested_due_month=suggested_due_month,
        suggested_due_day=suggested_due_day,
    )
    db.add(suggestion)
    db.flush()
    return suggestion
