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
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
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
    # Epic 7 (Nightly Transaction Backup): populated only by list_backup_folder_files
    # (used to sort by recency for retention, WR-14) -- None for the existing
    # list_folder_pdf_files/download_file callers, which never needed it.
    created_time: str | None = None


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
        files: list[DriveFileRef] = []
        page_token = None
        while True:
            # files().list() defaults to a 100-item page and silently truncates
            # without paging through nextPageToken -- explicit pageSize=1000 (the
            # API's own max) keeps this to one request for typical folder sizes,
            # with the loop below still paging further if more remain.
            results = (
                service.files()
                .list(q=query, fields="nextPageToken, files(id, name)", pageSize=1000, pageToken=page_token)
                .execute()
            )
            files.extend(DriveFileRef(id=f["id"], name=f["name"]) for f in results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break
        return files
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


# --- Epic 7 (Nightly Transaction Backup) additions below: all operate against the
# separate, dedicated backup Drive folder (settings.google_drive_backup_folder_id),
# never the statement-ingestion source folder above. ---

_BACKUP_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@retry_with_backoff()
def ensure_backup_folder_exists(db: Session, parent_folder_id: str) -> str:
    """Idempotent (WR-14): returns the existing `backup` subfolder's ID if one
    already exists under parent_folder_id, otherwise creates it."""
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        query = (
            f"'{parent_folder_id}' in parents and name = 'backup' "
            f"and mimeType = '{_BACKUP_FOLDER_MIME_TYPE}' and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
        existing = results.get("files", [])
        if existing:
            return existing[0]["id"]
        created = (
            service.files()
            .create(
                body={"name": "backup", "mimeType": _BACKUP_FOLDER_MIME_TYPE, "parents": [parent_folder_id]},
                fields="id",
            )
            .execute()
        )
        return created["id"]
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive ensure-backup-folder transient error: {exc}") from exc
        raise


@retry_with_backoff()
def upload_file(db: Session, folder_id: str, filename: str, content: bytes, mime_type: str) -> DriveFileRef:
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
        result = (
            service.files()
            .create(body={"name": filename, "parents": [folder_id]}, media_body=media, fields="id, name")
            .execute()
        )
        return DriveFileRef(id=result["id"], name=result["name"])
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive upload transient error: {exc}") from exc
        raise


@retry_with_backoff()
def list_backup_folder_files(db: Session, folder_id: str) -> list[DriveFileRef]:
    """Same pagination approach as list_folder_pdf_files -- no MIME-type filter
    (backup files are CSV, not PDF) since this only ever scans the dedicated
    `backup` subfolder, not a mixed-content folder."""
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        query = f"'{folder_id}' in parents and trashed=false"
        files: list[DriveFileRef] = []
        page_token = None
        while True:
            results = (
                service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, createdTime)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(
                DriveFileRef(id=f["id"], name=f["name"], created_time=f.get("createdTime"))
                for f in results.get("files", [])
            )
            page_token = results.get("nextPageToken")
            if not page_token:
                break
        return files
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive list backup files transient error: {exc}") from exc
        raise


@retry_with_backoff()
def delete_file(db: Session, file_ref: DriveFileRef) -> None:
    credentials = _load_credentials(db)
    try:
        service = build("drive", "v3", credentials=credentials)
        service.files().delete(fileId=file_ref.id).execute()
    except HttpError as exc:
        if exc.resp.status in _TRANSIENT_HTTP_STATUS:
            raise TransientError(f"Drive delete transient error: {exc}") from exc
        raise
