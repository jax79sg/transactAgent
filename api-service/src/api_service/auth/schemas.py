from datetime import datetime

from pydantic import BaseModel

from api_service.schemas import CamelModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(CamelModel):
    token: str
    expires_at: datetime
