"""Thin wrapper around Google Drive API. Reads the refresh token from `oauth_credentials`
(written by Unit 2's /drive/connect + /drive/callback flow) rather than running any
OAuth flow itself — see aidlc-docs/audit.md 2026-08-01 for why the flow lives in Unit 2.
"""

from dataclasses import dataclass

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy.orm import Session
import io

from ingestion_worker.clients.retry import TransientError, retry_with_backoff
from ingestion_worker.config import settings
from transactagent_db.models import OAuthCredential

_TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}


class DriveNotConnectedError(Exception):
    """Raised when no OAuthCredential row exists yet (US-1.1 — user hasn't connected Drive)."""


class DriveReauthRequiredError(Exception):
    """Raised when the stored refresh token itself is no longer valid (US-1.1 edge case:
    revoked/expired credentials — the run should fail at the run level, prompting the
    user to reconnect via Unit 2's /drive/connect)."""


@dataclass
class DriveFileRef:
    id: str
    name: str


def _load_credentials(db: Session) -> Credentials:
    row = db.query(OAuthCredential).filter_by(provider="google_drive").first()
    if row is None:
        raise DriveNotConnectedError("Google Drive has not been connected yet")

    credentials = Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise DriveReauthRequiredError(f"Drive refresh token is no longer valid: {exc}") from exc
    except TransportError as exc:
        raise TransientError(f"Drive token refresh network error: {exc}") from exc
    return credentials


@retry_with_backoff()
def list_folder_pdf_files(db: Session) -> list[DriveFileRef]:
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        query = f"'{settings.google_drive_folder_id}' in parents and mimeType='application/pdf' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        return [DriveFileRef(id=f["id"], name=f["name"]) for f in results.get("files", [])]
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive list files transient error: {exc}") from exc
        raise


@retry_with_backoff()
def download_file(db: Session, file_ref: DriveFileRef) -> bytes:
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        request = service.files().get_media(fileId=file_ref.id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive download transient error: {exc}") from exc
        raise
