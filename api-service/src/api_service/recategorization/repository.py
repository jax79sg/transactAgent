"""Query wrappers for RecategorizationProposal (Repository Layer, Epic 6) and
CategorizationDisagreement (Repository Layer, Matching Precision Refinement)."""

from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload
from transactagent_db.models import (
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    RecategorizationProposal,
    RecategorizationProposalStatus,
    Transaction,
)

ProposalSortByOption = Literal["date", "amount", "score", "source"]
SortDir = Literal["asc", "desc"]

_PROPOSAL_SORT_COLUMNS = {
    "date": Transaction.transaction_date,
    "amount": func.coalesce(Transaction.out_flow, Transaction.in_flow),
    "score": RecategorizationProposal.match_score,
    "source": RecategorizationProposal.source_bucket,
}


def _apply_proposal_sort(stmt: Select, sort_by: ProposalSortByOption, sort_dir: SortDir) -> Select:
    # Explicit join, not relying on the _EAGER_LOAD_OPTIONS joinedload for this --
    # joinedload's JOIN uses an anonymized alias for eager-loading the relationship,
    # not one addressable via a plain `Transaction.column` reference in order_by()
    # (transactions/repository.py's _apply_sort hit this same thing for its
    # category-name sort, hence its own explicit conditional join there).
    if sort_by in ("date", "amount"):
        stmt = stmt.join(Transaction, RecategorizationProposal.candidate_transaction_id == Transaction.id)
    column = _PROPOSAL_SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())
    # Tie-break on created_at (the previous, only ordering) so equal sort values
    # still get a stable, predictable order across pages rather than depending on
    # whatever order Postgres happens to return them in.
    return stmt.order_by(RecategorizationProposal.created_at.desc())

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


def list_pending(
    db: Session,
    page: int,
    page_size: int,
    sort_by: ProposalSortByOption = "date",
    sort_dir: SortDir = "desc",
) -> tuple[list[RecategorizationProposal], int]:
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
    )
    stmt = _apply_proposal_sort(stmt, sort_by, sort_dir)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
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
