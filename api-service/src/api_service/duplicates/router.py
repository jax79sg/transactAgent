from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db
from api_service.duplicates import service
from api_service.duplicates.schemas import (
    ComparisonDTO,
    OverrideResponse,
    PairDTO,
    PairPage,
    PendingPairCountResponse,
    RemovalRequest,
    ScanStatusDTO,
)

router = APIRouter(prefix="/duplicates", tags=["duplicates"], dependencies=[Depends(get_current_user_id)])


@router.get("/pairs", response_model=PairPage)
def list_pairs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PairPage:
    return service.list_pairs(db, page=page, page_size=page_size)


# Declared before /pairs/{pair_id}/... so "pending-count" is never read as a pair id.
@router.get("/pairs/pending-count", response_model=PendingPairCountResponse)
def get_pending_pair_count(db: Session = Depends(get_db)) -> PendingPairCountResponse:
    return PendingPairCountResponse(pending_count=service.get_pending_count(db))


@router.post("/pairs/{pair_id}/remove", response_model=PairDTO)
def confirm_removal(pair_id: UUID, request: RemovalRequest, db: Session = Depends(get_db)) -> PairDTO:
    return service.confirm_removal(db, pair_id, request)


@router.post("/pairs/{pair_id}/dismiss", response_model=PairDTO)
def dismiss_pair(pair_id: UUID, db: Session = Depends(get_db)) -> PairDTO:
    return service.dismiss_pair(db, pair_id)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDTO)
def get_comparison(comparison_id: UUID, db: Session = Depends(get_db)) -> ComparisonDTO:
    return service.get_comparison(db, comparison_id)


@router.post("/comparisons/{comparison_id}/override", response_model=OverrideResponse)
def override_skipped_file(comparison_id: UUID, db: Session = Depends(get_db)) -> OverrideResponse:
    return service.override_skipped_file(db, comparison_id)


@router.get("/scan-status", response_model=ScanStatusDTO)
def get_scan_status(db: Session = Depends(get_db)) -> ScanStatusDTO:
    return service.get_scan_status(db)


@router.post("/recheck", response_model=ScanStatusDTO)
def request_recheck(db: Session = Depends(get_db)) -> ScanStatusDTO:
    return service.request_recheck(db)
