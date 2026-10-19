"""Duplicate Review DTOs (functional-design/domain-entities.md, Epic 14). Field names are camelCase on
the wire (CamelModel); enumerated values are the stored snake_case strings, as every other router returns
an enum's `.value`."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from api_service.schemas import CamelModel


class StatementLabelDTO(CamelModel):
    content_hash: str
    file_name: str | None
    bank_name: str | None
    period_start: date
    period_end: date
    transaction_count: int


class RemovalPreviewDTO(CamelModel):
    """What a removal would delete, read live (AR-41). The first six are the dependents list the worker
    deletes (BR-51); `only_on_removed_copy` is the removed side's stored count minus the stored matched
    count, so the API holds no copy of the matching rule."""

    transactions: int
    statement_sections: int
    recategorization_jobs: int
    recategorization_proposals: int
    categorization_disagreements: int
    recurring_payment_matches: int
    corrections_lost: int
    only_on_removed_copy: int


class RemovalStatusDTO(CamelModel):
    job_id: UUID
    status: str  # queued | running | embeddings_pending | embeddings_failed | completed | failed
    failure_reason: str | None
    requested_at: datetime
    finished_at: datetime | None
    deleted_counts: dict | None


class PairDTO(CamelModel):
    id: UUID
    comparison_id: UUID
    status: str  # pending | removed | dismissed | superseded
    removal_offered: bool
    stale: bool
    keep: StatementLabelDTO
    remove: StatementLabelDTO
    corrections_on_kept: int | None
    corrections_on_removed: int | None
    preview: RemovalPreviewDTO | None
    removal: RemovalStatusDTO | None
    found_at: datetime


class PairPage(CamelModel):
    items: list[PairDTO]
    page: int
    page_size: int
    total_count: int


class PendingPairCountResponse(CamelModel):
    pending_count: int


class RemovalRequest(CamelModel):
    remove_statement_hash: str
    acknowledged_corrections_lost: int


class ComparisonRowDTO(CamelModel):
    rank: int
    transaction_date: date
    description: str
    out_flow: Decimal | None
    in_flow: Decimal | None
    currency: str
    marker: str  # also_on_other | only_on_this_one


class ComparisonSideDTO(CamelModel):
    label: StatementLabelDTO
    rows: list[ComparisonRowDTO]


class ComparisonDTO(CamelModel):
    id: UUID
    # skipped | ingest_at_next_run | ingested_at_your_request | removed | pair_pending | pair_dismissed | pair_superseded
    state: str
    reason: str
    matched_count: int
    match_ratio: Decimal
    earlier: ComparisonSideDTO
    later: ComparisonSideDTO
    this_file_side: str | None  # earlier | later, set only when the comparison belongs to a remembered file
    can_override: bool
    pair_id: UUID | None
    removal_offered: bool | None
    created_at: datetime


class OverrideResponse(CamelModel):
    comparison_id: UUID
    state: str  # ingest_at_next_run | ingested_at_your_request
    note: str | None


class ScanStatusDTO(CamelModel):
    last_completed_at: datetime | None
    pairs_found: int | None
    recheck_requested: bool
    detection_enabled: bool
