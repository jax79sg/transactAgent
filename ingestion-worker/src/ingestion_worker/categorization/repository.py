from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ingestion_worker.categorization.similarity import SimilarityCandidate
from transactagent_db.models import (
    Category,
    CategorySource,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    Transaction,
)


def list_similarity_candidates(db: Session) -> list[SimilarityCandidate]:
    """Past transactions with a confirmed category (excludes UNSURE, per business-logic-model.md)."""
    stmt = (
        select(Transaction.id, Transaction.description, Category.name, Transaction.category_source)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.category_source != CategorySource.UNSURE)
    )
    return [
        SimilarityCandidate(
            transaction_id=str(row.id),
            description=row.description,
            category_name=row.name,
            category_source=row.category_source.value,
        )
        for row in db.execute(stmt)
    ]


def list_active_category_names(db: Session) -> list[str]:
    stmt = select(Category.name).where(Category.active.is_(True))
    return list(db.scalars(stmt))


def find_category_by_name(db: Session, name: str) -> Category | None:
    return db.scalar(select(Category).where(Category.name == name))


def find_unsure_transactions(db: Session) -> list[Transaction]:
    stmt = select(Transaction).join(Category, Transaction.category_id == Category.id).where(
        Transaction.category_source == CategorySource.UNSURE
    )
    return list(db.scalars(stmt))


def get_transaction(db: Session, transaction_id: UUID) -> Transaction | None:
    return db.get(Transaction, transaction_id)


def find_categorized_transactions_excluding(
    db: Session, exclude_transaction_id: UUID, exclude_category_id: UUID
) -> list[Transaction]:
    """WR-9/WR-10 (Epic 6): candidates for the broadened, always-pending bucket --
    already-categorized transactions, excluding the source transaction itself (BR-15)
    and any transaction already at the category being proposed (a no-op match)."""
    stmt = (
        select(Transaction)
        .where(Transaction.category_source != CategorySource.UNSURE)
        .where(Transaction.id != exclude_transaction_id)
        .where(Transaction.category_id != exclude_category_id)
    )
    return list(db.scalars(stmt))


def record_proposal(
    db: Session,
    *,
    job_id: UUID,
    candidate_transaction_id: UUID,
    proposed_category_id: UUID,
    match_score: float,
    source_bucket: RecategorizationProposalSourceBucket,
    status: RecategorizationProposalStatus,
) -> RecategorizationProposal:
    """Epic 6: records one outcome of the broadened re-scan (WR-9/WR-10) -- an
    auto-applied change or a pending proposal. `resolved_at` is set immediately for
    `auto_applied` (it never passes through `pending`); left null otherwise, to be set
    by the API Service's Recategorization Review Component on approve/reject."""
    proposal = RecategorizationProposal(
        recategorization_job_id=job_id,
        candidate_transaction_id=candidate_transaction_id,
        proposed_category_id=proposed_category_id,
        match_score=Decimal(str(round(match_score, 2))),
        source_bucket=source_bucket,
        status=status,
        resolved_at=func.now() if status == RecategorizationProposalStatus.AUTO_APPLIED else None,
    )
    db.add(proposal)
    db.flush()
    return proposal
