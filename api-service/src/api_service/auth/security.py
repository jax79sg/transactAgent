"""Password hashing and JWT issuance/validation (business-logic-model.md — Auth Component).

Uses the `bcrypt` library directly rather than passlib's CryptContext: passlib is
unmaintained and its bcrypt backend self-test is incompatible with bcrypt>=4.0 (raises
ValueError during passlib's own internal wrap-bug detection), a known unresolved
upstream issue. Calling bcrypt directly avoids it entirely.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from api_service.config import settings


def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def issue_token(user_id: UUID) -> tuple[str, datetime]:
    """Issue a JWT with a sliding 24h expiry (Question 2 = A)."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {"sub": str(user_id), "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_token(token: str) -> UUID:
    """Decode and validate a JWT, returning the user id. Raises jwt exceptions on failure."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return UUID(payload["sub"])
