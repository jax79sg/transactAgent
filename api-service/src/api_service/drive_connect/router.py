from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.config import settings
from api_service.db import get_db
from api_service.drive_connect import service
from api_service.drive_connect.schemas import DriveAuthorizationUrl, DriveConnectionStatus

router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/connect", response_model=DriveAuthorizationUrl, dependencies=[Depends(get_current_user_id)])
def connect() -> DriveAuthorizationUrl:
    """Authenticated: returns the Google consent URL for the Frontend to navigate the
    browser to (a plain JSON response, not a server-side redirect, since this is called
    via fetch() from the SPA — the SPA itself performs `window.location = url`)."""
    return DriveAuthorizationUrl(authorization_url=service.build_authorization_url())


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """Unauthenticated: this is hit by Google's top-level browser redirect, which
    carries no Authorization header. CSRF protection comes from validating `state`
    against the one issued by /connect (see service.py)."""
    service.handle_callback(db, code=code, state=state)
    # frontend_origin may now be a comma-separated list (multi-origin CORS support,
    # added 2026-08-02); a redirect target needs exactly one URL, so use the first
    # (primary) configured origin.
    return RedirectResponse(url=f"{settings.frontend_origins[0]}/settings?driveConnected=true")


@router.get("/status", response_model=DriveConnectionStatus, dependencies=[Depends(get_current_user_id)])
def status(db: Session = Depends(get_db)) -> DriveConnectionStatus:
    return DriveConnectionStatus(connected=service.get_connection_status(db))
