from datetime import datetime
from decimal import Decimal
from uuid import UUID

from api_service.schemas import CamelModel
from api_service.transactions.schemas import CategoryRef, TransactionDTO


class ProposalDTO(CamelModel):
    id: UUID
    candidate_transaction: TransactionDTO
    proposed_category: CategoryRef
    match_score: Decimal
    source_bucket: str
    status: str
    created_at: datetime
    source_transaction_id: UUID


class ProposalPage(CamelModel):
    items: list[ProposalDTO]
    page: int
    page_size: int
    total_count: int


class PendingCountResponse(CamelModel):
    pending_count: int


class BulkProposalRequest(CamelModel):
    proposal_ids: list[UUID]


class BulkApproveResponse(CamelModel):
    approved_ids: list[UUID]
    failed_ids: list[UUID]


class BulkRejectResponse(CamelModel):
    rejected_ids: list[UUID]
    failed_ids: list[UUID]


class DisagreementDTO(CamelModel):
    id: UUID
    candidate_transaction: TransactionDTO
    similarity_category: CategoryRef
    llm_category: CategoryRef
    similarity_score: Decimal
    status: str
    resolved_category: CategoryRef | None
    created_at: datetime


class DisagreementPage(CamelModel):
    items: list[DisagreementDTO]
    page: int
    page_size: int
    total_count: int


class ResolveDisagreementRequest(CamelModel):
    chosen_category_id: UUID
