"""Recategorization Review business logic (business-logic-model.md — Recategorization
Review Component). Implements AR-11, AR-12, AR-13.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from api_service.errors import NotFoundError, ProposalNotPendingError
from api_service.recategorization import repository
from transactagent_db.models import CategorySource, RecategorizationProposal, RecategorizationProposalStatus


def list_pending_proposals(db: Session, page: int, page_size: int) -> tuple[list[RecategorizationProposal], int]:
    return repository.list_pending(db, page=page, page_size=page_size)


def get_pending_count(db: Session) -> int:
    return repository.count_pending(db)


def _get_pending_proposal(db: Session, proposal_id: UUID) -> RecategorizationProposal:
    proposal = repository.find_by_id(db, proposal_id)
    if proposal is None:
        raise NotFoundError(f"Recategorization proposal {proposal_id} not found")
    if proposal.status != RecategorizationProposalStatus.PENDING:
        raise ProposalNotPendingError(
            f"Recategorization proposal {proposal_id} is not pending (status={proposal.status.value})"
        )
    return proposal


def approve_proposal(db: Session, proposal_id: UUID) -> RecategorizationProposal:
    proposal = _get_pending_proposal(db, proposal_id)
    # Assign the relationship object, not just the FK column: setting only
    # category_id leaves the already-loaded candidate_transaction.category relationship
    # pointing at the OLD category for the rest of this request/session (SQLAlchemy
    # doesn't infer a relationship refresh from a raw scalar FK write). The committed
    # database row is correct either way, but the DTO built from this same object
    # immediately after would show stale data -- caught via live verification against
    # the real API, not by any mocked unit test. proposal.proposed_category is already
    # loaded and never mutated, so it's a safe, query-free source of truth here.
    proposal.candidate_transaction.category = proposal.proposed_category
    proposal.candidate_transaction.category_source = CategorySource.SIMILARITY
    proposal.status = RecategorizationProposalStatus.APPROVED
    proposal.resolved_at = func.now()
    db.flush()
    return proposal


def reject_proposal(db: Session, proposal_id: UUID) -> RecategorizationProposal:
    proposal = _get_pending_proposal(db, proposal_id)
    proposal.status = RecategorizationProposalStatus.REJECTED
    proposal.resolved_at = func.now()
    db.flush()
    return proposal


def bulk_approve(db: Session, proposal_ids: list[UUID]) -> tuple[list[UUID], list[UUID]]:
    """AR-11/AR-12: a bad id (not found, or not pending) is a per-item failure -- it
    does not abort the rest of the batch."""
    approved_ids: list[UUID] = []
    failed_ids: list[UUID] = []
    for proposal_id in proposal_ids:
        try:
            approve_proposal(db, proposal_id)
            approved_ids.append(proposal_id)
        except NotFoundError:
            failed_ids.append(proposal_id)
        except ProposalNotPendingError:
            failed_ids.append(proposal_id)
    return approved_ids, failed_ids


def bulk_reject(db: Session, proposal_ids: list[UUID]) -> tuple[list[UUID], list[UUID]]:
    rejected_ids: list[UUID] = []
    failed_ids: list[UUID] = []
    for proposal_id in proposal_ids:
        try:
            reject_proposal(db, proposal_id)
            rejected_ids.append(proposal_id)
        except NotFoundError:
            failed_ids.append(proposal_id)
        except ProposalNotPendingError:
            failed_ids.append(proposal_id)
    return rejected_ids, failed_ids
