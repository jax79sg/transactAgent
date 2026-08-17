"""Query wrappers for RecategorizationProposal (Repository Layer, Epic 6) and
CategorizationDisagreement (Repository Layer, Matching Precision Refinement)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from transactagent_db.models import (
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    RecategorizationProposal,
    RecategorizationProposalStatus,
    Transaction,
)

_EAGER_LOAD_OPTIONS = (
    joinedload(RecategorizationProposal.candidate_transaction).joinedload(Transaction.category),
    joinedload(RecategorizationProposal.proposed_category),
    joinedload(RecategorizationProposal.recategorization_job),
)

_DISAGREEMENT_EAGER_LOAD_OPTIONS = (
    joinedload(CategorizationDisagreement.transaction).joinedload(Transaction.category),
    joinedload(CategorizationDisagreement.similarity_category),
    joinedload(CategorizationDisagreement.llm_category),
    joinedload(CategorizationDisagreement.resolved_category),
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


def find_disagreement_by_id(db: Session, disagreement_id: UUID) -> CategorizationDisagreement | None:
    return db.get(CategorizationDisagreement, disagreement_id, options=_DISAGREEMENT_EAGER_LOAD_OPTIONS)


def list_pending_disagreements(db: Session, page: int, page_size: int) -> tuple[list[CategorizationDisagreement], int]:
    total_count = (
        db.scalar(
            select(func.count())
            .select_from(CategorizationDisagreement)
            .where(CategorizationDisagreement.status == CategorizationDisagreementStatus.PENDING)
        )
        or 0
    )
    stmt = (
        select(CategorizationDisagreement)
        .where(CategorizationDisagreement.status == CategorizationDisagreementStatus.PENDING)
        .options(*_DISAGREEMENT_EAGER_LOAD_OPTIONS)
        .order_by(CategorizationDisagreement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(stmt)), total_count


def count_pending_disagreements(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(CategorizationDisagreement)
            .where(CategorizationDisagreement.status == CategorizationDisagreementStatus.PENDING)
        )
        or 0
    )
