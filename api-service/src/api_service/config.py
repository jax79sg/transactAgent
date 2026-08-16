"""Environment-sourced configuration (NFR-4.1 — no secrets hardcoded)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    db_host: str = "database"
    db_port: int = 5432
    db_name: str = "transactagent"
    db_user: str
    db_password: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 24 * 60  # 24h sliding expiry, Question 2 = A

    # Comma-separated list, e.g. "http://localhost:8787,http://192.168.1.50:8787" --
    # supports accessing the app from more than one address (localhost on the host
    # machine, plus a LAN IP for other devices) without needing a single canonical
    # origin. Discovered as a real gap 2026-08-02: a user on their phone via the
    # host's LAN IP was rejected by CORS since only one exact origin was ever allowed.
    frontend_origin: str = "http://localhost:5173"

    @property
    def frontend_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    # Google Drive OAuth (US-1.1) — see drive_connect/ for the connect/callback flow.
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_redirect_uri: str = "http://localhost:7878/drive/callback"

    default_page_size: int = 50
    max_page_size: int = 200
    csv_export_max_rows: int = 50_000

    # Ask AI (US-6.1): synchronous Gemini text call from api-service itself, not
    # routed through ingestion-worker's job queue -- that queue processes one
    # ingestion run or recategorization job at a time (WR-8), so a queued "question"
    # job could sit behind a multi-minute ingestion run, unacceptable for what's
    # meant to feel like an interactive question-answer exchange.
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_assistant_max_transactions: int = 3000

    # Epic 8 (Recurring Payments): AR-15's due-soon lead window -- how many days
    # before an upcoming due date (or before the next cycle, once the current one
    # is already paid) status flips from "paid"/nothing to "due_soon".
    recurring_payment_due_soon_lead_days: int = 5

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
