from api_service.schemas import CamelModel


class DriveConnectionStatus(CamelModel):
    connected: bool
    # True when a credential is saved but Google refuses it, so ingestion and the nightly backup cannot reach Drive
    # until the owner reconnects (Google's consent screen, which only the owner can complete).
    needs_reconnect: bool = False


class DriveAuthorizationUrl(CamelModel):
    authorization_url: str
