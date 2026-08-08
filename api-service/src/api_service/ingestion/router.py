from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db
from api_service.ingestion import service
from api_service.ingestion.schemas import (
    RunFileDetail,
    RunHistoryPage,
    RunLogLine,
    RunStatusResponse,
    StartRunResponse,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"], dependencies=[Depends(get_current_user_id)])


def _to_status_dto(run) -> RunStatusResponse:
    return RunStatusResponse(
        run_id=run.id,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        files_found_count=run.files_found_count,
        files_processed_count=run.files_processed_count,
        files_skipped_count=run.files_skipped_count,
        files_failed_count=run.files_failed_count,
        cancel_requested_at=run.cancel_requested_at,
    )


@router.post("/runs", response_model=StartRunResponse, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    current_user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> StartRunResponse:
    run = service.start_run(db, triggered_by_user_id=current_user_id)
    return StartRunResponse(run_id=run.id)


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: UUID, db: Session = Depends(get_db)) -> RunStatusResponse:
    run = service.get_run_status(db, run_id)
    return _to_status_dto(run)


@router.post("/runs/{run_id}/cancel", response_model=RunStatusResponse)
def cancel_run(run_id: UUID, db: Session = Depends(get_db)) -> RunStatusResponse:
    run = service.cancel_run(db, run_id)
    return _to_status_dto(run)


@router.get("/runs", response_model=RunHistoryPage)
def list_run_history(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)
) -> RunHistoryPage:
    runs, total_count = service.list_run_history(db, page=page, page_size=page_size)
    return RunHistoryPage(
        items=[_to_status_dto(r) for r in runs], page=page, page_size=page_size, total_count=total_count
    )


@router.get("/runs/{run_id}/files", response_model=list[RunFileDetail])
def list_run_files(run_id: UUID, db: Session = Depends(get_db)) -> list[RunFileDetail]:
    files = service.list_run_files(db, run_id)
    return [
        RunFileDetail(
            id=f.id,
            drive_file_name=f.drive_file_name,
            outcome=f.outcome.value,
            failure_reason=f.failure_reason,
            transactions_extracted_count=f.transactions_extracted_count,
            processed_at=f.processed_at,
        )
        for f in files
    ]


@router.get("/runs/{run_id}/logs", response_model=list[RunLogLine])
def list_run_logs(
    run_id: UUID, after_id: int | None = Query(default=None, ge=0), db: Session = Depends(get_db)
) -> list[RunLogLine]:
    """Live log-tail polling: pass the highest `id` already received as `after_id` to
    get only new lines since then."""
    logs = service.list_run_logs(db, run_id, after_id=after_id)
    return [
        RunLogLine(id=log.id, logged_at=log.logged_at, level=log.level, logger_name=log.logger_name, message=log.message)
        for log in logs
    ]
