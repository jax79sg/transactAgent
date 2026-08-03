from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import OAuthCredential

PROVIDER = "google_drive"


def find_credential(db: Session) -> OAuthCredential | None:
    return db.scalar(select(OAuthCredential).where(OAuthCredential.provider == PROVIDER))


def upsert_credential(
    db: Session, *, refresh_token: str, access_token: str | None, access_token_expires_at: datetime | None
) -> OAuthCredential:
    existing = find_credential(db)
    if existing is not None:
        existing.refresh_token = refresh_token
        existing.access_token = access_token
        existing.access_token_expires_at = access_token_expires_at
        db.flush()
        return existing

    credential = OAuthCredential(
        provider=PROVIDER,
        refresh_token=refresh_token,
        access_token=access_token,
        access_token_expires_at=access_token_expires_at,
    )
    db.add(credential)
    db.flush()
    return credential
