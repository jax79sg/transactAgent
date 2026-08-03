"""FastAPI dependency enforcing AR-1 (authentication required) on protected routes."""

from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api_service.auth.security import decode_token
from api_service.errors import UnauthorizedError

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID:
    if credentials is None:
        raise UnauthorizedError("Missing Authorization header")
    try:
        return decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc
