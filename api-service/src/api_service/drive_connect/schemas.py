from api_service.schemas import CamelModel


class DriveConnectionStatus(CamelModel):
    connected: bool


class DriveAuthorizationUrl(CamelModel):
    authorization_url: str
