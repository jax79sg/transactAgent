"""Environment-sourced configuration (NFR-4.1)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    db_host: str = "database"
    db_port: int = 5432
    db_name: str = "transactagent"
    db_user: str
    db_password: str

    gemini_api_key: str
    openrouter_api_key: str
    # Model identifiers are configuration, not code (per user request 2026-08-01) --
    # both providers evolve their lineups independently of this codebase; changing
    # models should never require a rebuild. Defaults match what was explicitly
    # confirmed against each provider's docs (see gemini_client.py / openrouter_client.py
    # for the "why these defaults" rationale and source links).
    # gemini-3.1-flash-lite was found (2026-08-02) to consistently transpose day/month
    # for at least one bank's day-first-printed dates (OCBC); gemini-3.5-flash-lite was
    # verified against the real failing statement (3/3 clean runs, 0 invalid dates) to
    # not exhibit this -- see aidlc-docs/audit.md.
    gemini_model: str = "gemini-3.5-flash-lite"
    openrouter_model: str = "openrouter/free"
    # The categorization LLM client (openrouter_client.py) uses the `openai` SDK
    # pointed at this base_url, so it works against any OpenAI-compatible chat
    # completions endpoint, not just OpenRouter itself -- e.g. a local model server
    # (per user request 2026-08-01, swapped to a locally-hosted omlx-server instance
    # after hitting OpenRouter's free-tier rate limits). Override alongside
    # openrouter_api_key/openrouter_model when pointing elsewhere.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Needed to refresh the Drive access token via the refresh token Unit 2 obtained
    # (Google's token-refresh request requires client_id + client_secret, not just the
    # refresh token itself) — same OAuth client as Unit 2, not a separate one.
    google_oauth_client_id: str
    google_oauth_client_secret: str
    # Defaults to the folder given in the original project request; override via env
    # if a different Drive folder should be scanned.
    google_drive_folder_id: str = "1qeJblYSk-E6BH6dhenbc8Vd0xxRkZor0"

    heartbeat_file: str = "/tmp/worker-heartbeat"
    poll_interval_seconds: float = 5.0

    similarity_threshold: float = 85.0
    # WR-9 (Epic 6): the retroactive re-scan's UNSURE-bucket auto-apply cutoff --
    # deliberately well above similarity_threshold, since a match at this tier writes
    # directly to a transaction with no human review (unlike a match between
    # similarity_threshold and this value, which becomes a reviewable proposal
    # instead). Tuned during Code Generation/testing, same as similarity_threshold
    # itself (WR-3) -- not an exact science, just a defensible starting point.
    recategorization_auto_apply_threshold: float = 97.0
    extraction_confidence_threshold: str = "medium"  # "low" | "medium" | "high"

    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 2.0

    reporting_currency: str = "SGD"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
