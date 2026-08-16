from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db
from api_service.recurring_payments import service
from api_service.recurring_payments.schemas import (
    AddFromDetectionSuggestionRequest,
    BulkImportRequest,
    BulkImportResponse,
    DetectionSuggestionDTO,
    RecurringPaymentCreateRequest,
    RecurringPaymentDTO,
    RecurringPaymentMatchDTO,
    RecurringPaymentsStatusSummaryDTO,
    RecurringPaymentUpdateRequest,
)

router = APIRouter(
    prefix="/recurring-payments", tags=["recurring-payments"], dependencies=[Depends(get_current_user_id)]
)


@router.get("", response_model=list[RecurringPaymentDTO])
def list_recurring_payments(db: Session = Depends(get_db)) -> list[RecurringPaymentDTO]:
    return service.list_recurring_payments(db)


@router.post("", response_model=RecurringPaymentDTO, status_code=status.HTTP_201_CREATED)
def create_recurring_payment(
    request: RecurringPaymentCreateRequest, db: Session = Depends(get_db)
) -> RecurringPaymentDTO:
    return service.create_recurring_payment(db, request)


@router.put("/{payment_id}", response_model=RecurringPaymentDTO)
def update_recurring_payment(
    payment_id: UUID, request: RecurringPaymentUpdateRequest, db: Session = Depends(get_db)
) -> RecurringPaymentDTO:
    return service.update_recurring_payment(db, payment_id, request)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_payment(payment_id: UUID, db: Session = Depends(get_db)) -> None:
    service.delete_recurring_payment(db, payment_id)


@router.post("/bulk-import", response_model=BulkImportResponse)
def bulk_import_recurring_payments(request: BulkImportRequest, db: Session = Depends(get_db)) -> BulkImportResponse:
    return service.bulk_import_recurring_payments(db, request)


@router.get("/matches", response_model=list[RecurringPaymentMatchDTO])
def list_pending_matches(db: Session = Depends(get_db)) -> list[RecurringPaymentMatchDTO]:
    return service.list_pending_matches(db)


@router.post("/matches/{match_id}/approve", response_model=RecurringPaymentMatchDTO)
def approve_match(match_id: UUID, db: Session = Depends(get_db)) -> RecurringPaymentMatchDTO:
    return service.approve_match(db, match_id)


@router.post("/matches/{match_id}/reject", response_model=RecurringPaymentMatchDTO)
def reject_match(match_id: UUID, db: Session = Depends(get_db)) -> RecurringPaymentMatchDTO:
    return service.reject_match(db, match_id)


@router.get("/detection-suggestions", response_model=list[DetectionSuggestionDTO])
def list_detection_suggestions(db: Session = Depends(get_db)) -> list[DetectionSuggestionDTO]:
    return service.list_detection_suggestions(db)


@router.post("/detection-suggestions/{suggestion_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_detection_suggestion(suggestion_id: UUID, db: Session = Depends(get_db)) -> None:
    service.dismiss_detection_suggestion(db, suggestion_id)


@router.post("/detection-suggestions/{suggestion_id}/add", response_model=RecurringPaymentDTO)
def add_from_detection_suggestion(
    suggestion_id: UUID,
    request: AddFromDetectionSuggestionRequest = AddFromDetectionSuggestionRequest(),
    db: Session = Depends(get_db),
) -> RecurringPaymentDTO:
    return service.add_from_detection_suggestion(db, suggestion_id, request)


@router.get("/status", response_model=RecurringPaymentsStatusSummaryDTO)
def get_status_summary(db: Session = Depends(get_db)) -> RecurringPaymentsStatusSummaryDTO:
    return service.get_status_summary(db)
