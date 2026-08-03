"""Query wrappers for RecategorizationProposal (Repository Layer, Epic 6)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from transactagent_db.models import RecategorizationProposal, RecategorizationProposalStatus, Transaction

_EAGER_LOAD_OPTIONS = (
    joinedload(RecategorizationProposal.candidate_transaction).joinedload(Transaction.category),
    joinedload(RecategorizationProposal.proposed_category),
    joinedload(RecategorizationProposal.recategorization_job),
)


def find_by_id(db: Session, proposal_id: UUID) -> RecategorizationProposal | None:
    return db.get(RecategorizationProposal, proposal_id, options=_EAGER_LOAD_OPTIONS)


def list_pending(db: Session, page: int, page_size: int) -> tuple[list[RecategorizationProposal], int]:
    total_count = (
        db.scalar(
            select(func.count())
            .select_from(RecategorizationProposal)
            .where(RecategorizationProposal.status == RecategorizationProposalStatus.PENDING)
        )
        or 0
    )
    stmt = (
        select(RecategorizationProposal)
        .where(RecategorizationProposal.status == RecategorizationProposalStatus.PENDING)
        .options(*_EAGER_LOAD_OPTIONS)
        .order_by(RecategorizationProposal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(stmt)), total_count


def count_pending(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(RecategorizationProposal)
            .where(RecategorizationProposal.status == RecategorizationProposalStatus.PENDING)
        )
        or 0
    )
