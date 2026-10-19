"""Unauthenticated release-number endpoint (issue #27): lets the interface show which release the server is on,
and lets anyone see at a glance when the interface and the server have drifted apart."""

from fastapi import APIRouter
from transactagent_db.version import app_version

from api_service.schemas import CamelModel

router = APIRouter(tags=["version"])


class VersionResponse(CamelModel):
    version: str


@router.get("/version", response_model=VersionResponse)
def get_version() -> VersionResponse:
    return VersionResponse(version=app_version())
