"""Google OAuth connect/callback flow for Google Drive access (US-1.1).

Retroactively added during Unit 3's NFR Requirements — see aidlc-docs/audit.md
2026-08-01. Unit 3 (the actual Drive Connector) has no browser-facing interface, so
Unit 2 handles the interactive OAuth handshake and persists the resulting refresh
token to the shared database for Unit 3 to read.

Scope was originally read-only Drive access, since the app only ever read PDFs.
Epic 7 (Nightly Transaction Backup) needs to create/write/delete files in a
dedicated backup folder identified by an arbitrary folder ID the user shares (not
a folder the app itself created, and not selected via a Drive file picker) --
`drive.file` scope only grants access to app-created/app-opened files, which a
live 403 "insufficientPermissions" test against the real API confirmed does not
cover writing into an arbitrary externally-shared folder ID the same way
`drive.readonly` already covers *reading* an arbitrary shared folder ID for
ingestion. The full `drive` scope is the narrowest scope that reliably supports
that "arbitrary folder ID, not app-created" access pattern for both read and
write -- see aidlc-docs/audit.md 2026-08-08. Existing connections must be
re-authorized (Settings -> Connect Google Drive) for this broader scope to take
effect; a previously-granted refresh token cannot retroactively gain scope.
"""

import logging
import secrets
import time

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from api_service.config import settings
from api_service.drive_connect import repository
from api_service.errors import ApiError

SCOPES = ["https://www.googleapis.com/auth/drive"]

# In-memory CSRF state store: single-process personal app, no need for a DB/cache
# table for a short-lived (few-minutes) OAuth handshake token. Also holds each
# state's PKCE code_verifier -- google-auth-oauthlib's Flow defaults to
# autogenerate_code_verifier=True, so build_authorization_url()'s Flow instance
# generates one and sends its hash (code_challenge) to Google; that same raw
# verifier must be replayed in handle_callback()'s token exchange (a *different*
# Flow instance, since HTTP is stateless), or Google rejects the exchange with
# "invalid_grant: Missing code verifier."
_STATE_TTL_SECONDS = 600
_pending_states: dict[str, tuple[float, str]] = {}


class InvalidOAuthStateError(ApiError):
    status_code = 400
    error_code = "invalid_oauth_state"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_oauth_redirect_uri],
        }
    }


def _prune_expired_states() -> None:
    now = time.time()
    expired = [s for s, (issued_at, _) in _pending_states.items() if now - issued_at > _STATE_TTL_SECONDS]
    for s in expired:
        del _pending_states[s]


def build_authorization_url() -> str:
    _prune_expired_states()
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=settings.google_oauth_redirect_uri)
    state = secrets.token_urlsafe(32)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",  # required to receive a refresh_token
        prompt="consent",  # force consent screen so a refresh_token is issued even on reconnect
        state=state,
    )
    _pending_states[state] = (time.time(), flow.code_verifier)
    return authorization_url


def handle_callback(db: Session, *, code: str, state: str) -> None:
    _prune_expired_states()
    if state not in _pending_states:
        raise InvalidOAuthStateError("OAuth state is missing, expired, or already used")
    _, code_verifier = _pending_states.pop(state)

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
        code_verifier=code_verifier,
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials

    if credentials.refresh_token is None:
        raise ApiError(
            "Google did not return a refresh token — try disconnecting Drive access in your "
            "Google Account settings and reconnecting",
            details={},
        )

    repository.upsert_credential(
        db,
        refresh_token=credentials.refresh_token,
        access_token=credentials.token,
        access_token_expires_at=credentials.expiry,
    )


logger = logging.getLogger(__name__)

# Settings should not hang because Google is slow: a status check that cannot be answered quickly says nothing.
_GOOGLE_TIMEOUT_SECONDS = 5


class _QuickRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = _GOOGLE_TIMEOUT_SECONDS
        return super().__call__(*args, **kwargs)


def _google_refuses(credential) -> bool:
    """True only when Google itself answers that the saved sign-in no longer works (revoked, expired, or the client
    changed): the same RefreshError the worker turns into "Drive refresh token is no longer valid" on every ingestion
    download and nightly backup. A network failure, a timeout or anything unexpected says nothing about the credential,
    so it is not reported as broken (a status screen that cries wolf is worse than one that is silent)."""
    credentials = Credentials(
        token=credential.access_token,
        refresh_token=credential.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
    )
    try:
        credentials.refresh(_QuickRequest())
    except RefreshError:
        return True
    except Exception:  # includes the transport errors; see the docstring
        logger.info("Could not check the Drive credential with Google; treating it as unknown", exc_info=True)
    return False


def get_connection_status(db: Session) -> tuple[bool, bool]:
    """(connected, needs_reconnect). `connected` is whether a credential is saved; `needs_reconnect` is whether Google
    refuses it (issue #70: Settings said "Connected" for weeks while every Drive call failed)."""
    credential = repository.find_credential(db)
    if credential is None:
        return False, False
    return True, _google_refuses(credential)
