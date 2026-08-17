"""Unauthenticated health endpoint (NFR Design — used by docker-compose healthcheck)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api_service.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception:  # noqa: BLE001 - any DB failure means "unavailable", not a 500
        return JSONResponse(status_code=503, content={"status": "unavailable"})
