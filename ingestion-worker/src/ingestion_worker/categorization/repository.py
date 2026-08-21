from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    Category,
    CategorySource,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    Transaction,
)

from ingestion_worker.categorization.similarity import SimilarityCandidate


def list_similarity_candidates(db: Session) -> list[SimilarityCandidate]:
    """Past transactions with a confirmed category (excludes UNSURE, per business-logic-model.md).

    `amount` is out_flow or in_flow, whichever is set (BR-2: exactly one always is)
    -- the sign/direction doesn't matter for similarity matching, only the
    magnitude, per find_best_match's amount-range gate.
    """
    stmt = (
        select(
            Transaction.id,
            Transaction.description,
            Category.name,
            Transaction.category_source,
            func.coalesce(Transaction.out_flow, Transaction.in_flow).label("amount"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.category_source != CategorySource.UNSURE)
    )
    return [
        SimilarityCandidate(
            transaction_id=str(row.id),
            description=row.description,
            category_name=row.name,
            category_source=row.category_source.value,
            amount=row.amount,
        )
        for row in db.execute(stmt)
    ]


def get_similarity_candidates_by_ids(db: Session, transaction_ids: list[str]) -> dict[str, SimilarityCandidate]:
    """Epic 9 (WR-21/23): fetches full candidate rows for a Vector Store Client
    nearest-neighbor result (which only returns entity IDs + scores, not the
    category_source/amount needed to apply the same amount-gate + manual-precedence
    filtering the fuzzy-text path already applies). Keyed by transaction_id (str)
    for easy lookup against the neighbor list; an ID with no matching row (a stale
    vector-store entry for a deleted transaction) is simply absent from the result,
    not an error."""
    if not transaction_ids:
        return {}
    stmt = (
        select(
            Transaction.id,
            Transaction.description,
            Category.name,
            Transaction.category_source,
            func.coalesce(Transaction.out_flow, Transaction.in_flow).label("amount"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.id.in_(transaction_ids))
    )
    return {
        str(row.id): SimilarityCandidate(
            transaction_id=str(row.id),
            description=row.description,
            category_name=row.name,
            category_source=row.category_source.value,
            amount=row.amount,
        )
        for row in db.execute(stmt)
    }


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


def record_disagreement(
    db: Session,
    *,
    transaction_id: UUID,
    similarity_category_id: UUID,
    llm_category_id: UUID,
    similarity_score: float,
) -> CategorizationDisagreement:
    """Matching Precision Refinement (WR-28): records a genuine categorization
    disagreement -- called by the Orchestrator immediately after the transaction
    itself is persisted (a disagreement needs a real transaction_id, which doesn't
    exist yet at categorize()'s own call time, see domain-entities.md's
    DisagreementInfo)."""
    disagreement = CategorizationDisagreement(
        transaction_id=transaction_id,
        similarity_category_id=similarity_category_id,
        llm_category_id=llm_category_id,
        similarity_score=Decimal(str(round(similarity_score, 2))),
        status=CategorizationDisagreementStatus.PENDING,
    )
    db.add(disagreement)
    db.flush()
    return disagreement
