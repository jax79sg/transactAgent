"""Environment-sourced configuration (NFR-4.1 — no secrets hardcoded)."""

from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Configurable Application Settings (AR-32): same shared override file and mechanism
# as Ingestion Worker Service's WR-33 -- see that unit's business-rules.md for the
# full reasoning. A fixed infrastructure path, not itself a user-tunable field.
SETTINGS_OVERRIDE_FILE = "/config/overrides/settings.env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

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
    # is already paid) status flips from "paid"/nothing to "due_soon". This is the
    # MONTHLY default; a per-payment RecurringPayment.due_soon_lead_days override
    # takes priority over either default (see recurring_payments/service.py's
    # _resolve_lead_days) -- issue #15: a single lead time couldn't give an annual
    # bill meaningfully more advance notice than a monthly one.
    recurring_payment_due_soon_lead_days: int = 5
    recurring_payment_due_soon_lead_days_annual: int = 30

    # --- Display-only mirror of Ingestion Worker's own settings (added 2026-08-16,
    # Configurable Application Settings, found after live verification showed the
    # Settings page reporting stale Python defaults instead of the deployment's real
    # values, e.g. OPENROUTER_MODEL) ---
    #
    # api-service never uses these fields functionally -- they exist ONLY so
    # app_settings/service.py can report each Ingestion-Worker-owned setting's real,
    # currently-effective value (override file, else whatever docker-compose/.env
    # actually supplied, else the built-in default) rather than a hardcoded catalog
    # default that silently drifts from what's really deployed. This works because
    # docker-compose.yml maps the exact same environment: entries onto BOTH
    # containers (Infrastructure Design addendum) and both Settings classes share
    # the identical settings_customise_sources() precedence (WR-33/AR-32) -- so this
    # object's values are guaranteed to agree with Ingestion Worker's own, without
    # api-service ever needing to call it directly. Defaults below are copied from
    # ingestion_worker/config.py and must be kept in sync with it (see that file for
    # the full per-field rationale/history -- not repeated here).
    similarity_threshold: float = 85.0
    similarity_amount_ratio_tolerance: float = 4.0
    similarity_amount_absolute_floor: float = 5.0
    recategorization_auto_apply_threshold: float = 97.0
    extraction_confidence_threshold: str = "medium"
    poll_interval_seconds: float = 5.0
    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 2.0
    reporting_currency: str = "SGD"
    recurring_payment_match_window_days: int = 5
    recurring_payment_trusted_amount_ratio_tolerance: float = 1.15
    recurring_payment_trusted_amount_absolute_floor: float = 5.0
    recurring_payment_detection_scan_interval_hours: int = 24
    recurring_payment_detection_min_occurrences: int = 2
    recurring_payment_detection_cadence_min_days: int = 25
    recurring_payment_detection_cadence_max_days: int = 35
    # Issue #15: a second, much wider cadence window so the detection scan can also
    # recognize a genuinely annual pattern (e.g. a once-a-year renewal), alongside
    # (not instead of) the monthly window above -- see ingestion_worker/
    # recurring_payments/service.py's _has_annual_cadence. 350-380 gives real
    # calendar slack (leap years, a bill landing on a slightly different weekday)
    # without coming anywhere near the monthly window's 35-day ceiling, so a
    # short-cadence pattern (e.g. a daily meal purchase) can never satisfy either.
    recurring_payment_detection_annual_cadence_min_days: int = 350
    recurring_payment_detection_annual_cadence_max_days: int = 380
    qdrant_host: str = "vector-db"
    qdrant_port: int = 6333
    embedding_base_url: str = ""
    embedding_model: str = "embeddinggemma-300m"
    embedding_similarity_threshold: float = 0.82
    embedding_top_k: int = 5
    embedding_batch_size: int = 50
    embedding_dimensions: int = 768
    llm_classification_concurrency: int = 5
    llm_classification_batch_size: int = 10
    embedding_price_bucket_boundaries: str = "1,5,10,20,50,100,200,500,1000,2000,5000"
    embedding_llm_agreement_boost: float = 0.05
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    backup_schedule_hour: int = 2
    backup_retention_count: int = 7

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """AR-32: identical mechanism to Ingestion Worker Service's WR-33 -- the
        settings-override file takes the HIGHEST precedence, checked before process
        env. See that unit's business-rules.md for the full empirically-verified
        reasoning; not re-derived independently here."""
        override_source = DotEnvSettingsSource(settings_cls, env_file=SETTINGS_OVERRIDE_FILE)
        return (override_source, init_settings, env_settings, dotenv_settings, file_secret_settings)


settings = Settings()
