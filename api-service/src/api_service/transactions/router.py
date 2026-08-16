from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db
from api_service.transactions import service
from api_service.transactions.schemas import (
    CategoryCorrectionRequest,
    CategoryRef,
    GroupSummary,
    TransactionDTO,
    TransactionFilter,
    TransactionListQuery,
    TransactionPage,
    TransactionUpdatedResponse,
)

router = APIRouter(prefix="/transactions", tags=["transactions"], dependencies=[Depends(get_current_user_id)])


def _to_dto(txn) -> TransactionDTO:
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


@router.get("", response_model=TransactionPage)
def list_transactions(query: TransactionListQuery = Depends(), db: Session = Depends(get_db)) -> TransactionPage:
    items, total_count, groups = service.list_transactions(db, query)
    return TransactionPage(
        items=[_to_dto(t) for t in items],
        page=query.page,
        page_size=query.page_size,
        total_count=total_count,
        groups=[GroupSummary(**g) for g in groups] if groups else None,
    )


@router.get("/banks", response_model=list[str])
def list_banks(db: Session = Depends(get_db)) -> list[str]:
    return service.list_distinct_banks(db)


@router.get("/export.csv", response_class=PlainTextResponse)
def export_transactions_csv(filters: TransactionFilter = Depends(), db: Session = Depends(get_db)) -> str:
    return service.export_transactions_csv(db, filters)


@router.put("/{transaction_id}/category", response_model=TransactionUpdatedResponse)
def correct_transaction_category(
    transaction_id: UUID, payload: CategoryCorrectionRequest, db: Session = Depends(get_db)
) -> TransactionUpdatedResponse:
    txn, job = service.correct_transaction_category(db, transaction_id, payload.category_id)
    return TransactionUpdatedResponse(transaction=_to_dto(txn), recategorization_job_id=job.id)
