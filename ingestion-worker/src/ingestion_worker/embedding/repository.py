from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import EmbeddingStatus, RecurringPayment, Transaction


def list_pending_transactions(db: Session, limit: int) -> list[Transaction]:
    """WR-26: deterministic order (ascending created_at, id) so an interrupted-and-
    resumed batch always makes visible forward progress (NFR-4)."""
    stmt = (
        select(Transaction)
        .where(Transaction.embedding_status == EmbeddingStatus.PENDING)
        .order_by(Transaction.created_at.asc(), Transaction.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_pending_recurring_payments(db: Session, limit: int) -> list[RecurringPayment]:
    stmt = (
        select(RecurringPayment)
        .where(RecurringPayment.embedding_status == EmbeddingStatus.PENDING)
        .order_by(RecurringPayment.created_at.asc(), RecurringPayment.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def mark_transaction_embedded(db: Session, transaction: Transaction) -> None:
    """WR-26: only called after the vector store upsert has already succeeded --
    write ordering is what makes an interrupted batch crash-safe."""
    transaction.embedding_status = EmbeddingStatus.COMPLETED
    db.flush()


def mark_recurring_payment_embedded(db: Session, payment: RecurringPayment) -> None:
    payment.embedding_status = EmbeddingStatus.COMPLETED
    db.flush()
