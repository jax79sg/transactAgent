"""Account Management endpoints (Epic 13, `domain-entities.md`). Every request needs the same login as the rest of the
API (NFR-AB-6)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.accounts import service
from api_service.accounts.schemas import (
    AccountDTO,
    AccountListResponse,
    AccountUpdateRequest,
    AnchorRequest,
    AnchorResponse,
    MergeRequest,
)
from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(get_current_user_id)])


@router.get("", response_model=AccountListResponse)
def list_accounts(db: Session = Depends(get_db)) -> AccountListResponse:
    return service.list_accounts(db)


@router.patch("/{account_id}", response_model=AccountDTO)
def update_account(account_id: UUID, request: AccountUpdateRequest, db: Session = Depends(get_db)) -> AccountDTO:
    return service.update_account(db, account_id, request)


@router.put("/{account_id}/anchor", response_model=AnchorResponse)
def set_anchor(account_id: UUID, request: AnchorRequest, db: Session = Depends(get_db)) -> AnchorResponse:
    return service.set_anchor(db, account_id, request)


@router.post("/{account_id}/merge", response_model=AccountDTO)
def merge_accounts(account_id: UUID, request: MergeRequest, db: Session = Depends(get_db)) -> AccountDTO:
    return service.merge_accounts(db, account_id, request)
