from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.auth import repository
from api_service.auth.schemas import LoginRequest, LoginResponse
from api_service.auth.security import issue_token, verify_password
from api_service.db import get_db
from api_service.errors import UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = repository.find_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")

    token, expires_at = issue_token(user.id)
    return LoginResponse(token=token, expires_at=expires_at)
