from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db
from api_service.recategorization import service
from api_service.recategorization.repository import ProposalSortByOption, SortDir
from api_service.recategorization.schemas import (
    BulkApproveResponse,
    BulkProposalRequest,
    BulkRejectResponse,
    DisagreementDTO,
    DisagreementPage,
    PendingCountResponse,
    ProposalDTO,
    ProposalPage,
    ResolveDisagreementRequest,
)
from api_service.transactions.schemas import CategoryRef, TransactionDTO

router = APIRouter(prefix="/recategorization", tags=["recategorization"], dependencies=[Depends(get_current_user_id)])


def _to_transaction_dto(txn) -> TransactionDTO:
    return TransactionDTO(
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
    )


def _to_proposal_dto(proposal) -> ProposalDTO:
    return ProposalDTO(
        id=proposal.id,
        candidate_transaction=_to_transaction_dto(proposal.candidate_transaction),
        proposed_category=CategoryRef(id=proposal.proposed_category.id, name=proposal.proposed_category.name),
        match_score=proposal.match_score,
        source_bucket=proposal.source_bucket.value,
        status=proposal.status.value,
        created_at=proposal.created_at,
        source_transaction_id=proposal.recategorization_job.source_transaction_id,
    )


def _to_disagreement_dto(disagreement) -> DisagreementDTO:
    return DisagreementDTO(
        id=disagreement.id,
        candidate_transaction=_to_transaction_dto(disagreement.transaction),
        similarity_category=CategoryRef(id=disagreement.similarity_category.id, name=disagreement.similarity_category.name),
        llm_category=CategoryRef(id=disagreement.llm_category.id, name=disagreement.llm_category.name),
        similarity_score=disagreement.similarity_score,
        status=disagreement.status.value,
        resolved_category=(
            CategoryRef(id=disagreement.resolved_category.id, name=disagreement.resolved_category.name)
            if disagreement.resolved_category is not None
            else None
        ),
        created_at=disagreement.created_at,
    )


@router.get("/proposals", response_model=ProposalPage)
def list_pending_proposals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: ProposalSortByOption = Query(default="date"),
    sort_dir: SortDir = Query(default="desc"),
    db: Session = Depends(get_db),
) -> ProposalPage:
    proposals, total_count = service.list_pending_proposals(
        db, page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir
    )
    return ProposalPage(
        items=[_to_proposal_dto(p) for p in proposals], page=page, page_size=page_size, total_count=total_count
    )


@router.get("/proposals/pending-count", response_model=PendingCountResponse)
def get_pending_count(db: Session = Depends(get_db)) -> PendingCountResponse:
    return PendingCountResponse(pending_count=service.get_pending_count(db))


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalDTO)
def approve_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> ProposalDTO:
    proposal = service.approve_proposal(db, proposal_id)
    return _to_proposal_dto(proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalDTO)
def reject_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> ProposalDTO:
    proposal = service.reject_proposal(db, proposal_id)
    return _to_proposal_dto(proposal)


@router.post("/proposals/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve_proposals(request: BulkProposalRequest, db: Session = Depends(get_db)) -> BulkApproveResponse:
    approved_ids, failed_ids = service.bulk_approve(db, request.proposal_ids)
    return BulkApproveResponse(approved_ids=approved_ids, failed_ids=failed_ids)


@router.post("/proposals/bulk-reject", response_model=BulkRejectResponse)
def bulk_reject_proposals(request: BulkProposalRequest, db: Session = Depends(get_db)) -> BulkRejectResponse:
    rejected_ids, failed_ids = service.bulk_reject(db, request.proposal_ids)
    return BulkRejectResponse(rejected_ids=rejected_ids, failed_ids=failed_ids)


@router.get("/disagreements", response_model=DisagreementPage)
def list_pending_disagreements(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)
) -> DisagreementPage:
    disagreements, total_count = service.list_pending_disagreements(db, page=page, page_size=page_size)
    return DisagreementPage(
        items=[_to_disagreement_dto(d) for d in disagreements], page=page, page_size=page_size, total_count=total_count
    )


@router.post("/disagreements/{disagreement_id}/resolve", response_model=DisagreementDTO)
def resolve_disagreement(
    disagreement_id: UUID, request: ResolveDisagreementRequest, db: Session = Depends(get_db)
) -> DisagreementDTO:
    disagreement = service.resolve_disagreement(db, disagreement_id, request.chosen_category_id)
    return _to_disagreement_dto(disagreement)


@router.post("/disagreements/{disagreement_id}/reject", response_model=DisagreementDTO)
def reject_disagreement(disagreement_id: UUID, db: Session = Depends(get_db)) -> DisagreementDTO:
    disagreement = service.reject_disagreement(db, disagreement_id)
    return _to_disagreement_dto(disagreement)
