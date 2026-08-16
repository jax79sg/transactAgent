"""Environment-sourced configuration (NFR-4.1)."""

from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Configurable Application Settings: the shared, non-secret override file both
# api-service and ingestion-worker mount from the same Docker volume (Infrastructure
# Design). A fixed infrastructure path, not itself a user-tunable Settings field.
SETTINGS_OVERRIDE_FILE = "/config/overrides/settings.env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

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
    # No default -- the Drive folder to scan is specific to each deployment, set via env.
    google_drive_folder_id: str
    # Epic 7 (Nightly Transaction Backup): deliberately a SEPARATE Drive folder from
    # google_drive_folder_id above, not a subfolder of it -- per the user's explicit
    # single-point-of-failure concern raised during Requirements Analysis (losing the
    # source folder would otherwise lose the backups too). The `backup` subfolder is
    # created under this folder on first use (see clients/drive_client.py). No default,
    # same reasoning as google_drive_folder_id above.
    google_drive_backup_folder_id: str
    # FR-2 default: no specific time was required, so 02:00 server/container local
    # time was chosen as a documented assumption (low-traffic window, no conflict
    # with the 5s ingestion poll loop) -- see nightly-backup-requirements.md.
    backup_schedule_hour: int = 2
    # FR-7 (WR-14): number of most-recent backup files kept in the `backup` subfolder.
    backup_retention_count: int = 7

    heartbeat_file: str = "/tmp/worker-heartbeat"
    poll_interval_seconds: float = 5.0

    similarity_threshold: float = 85.0
    # A same-merchant text match (WR-3) is only eligible if the two amounts are also
    # "in range" of each other: within similarity_amount_absolute_floor (handles
    # small-value line items, e.g. two currency-conversion fees of $0.01 and $0.27),
    # OR the larger is at most similarity_amount_ratio_tolerance times the smaller
    # (handles ordinary month-to-month drift on a recurring bill without accepting
    # wildly different amounts just because the merchant text matches -- e.g. a $699
    # car loan installment and an $81.70 conservancy fee both paid via the same AXS
    # bill-pay kiosk, a real incident this was added for, see aidlc-docs/audit.md
    # 2026-08-06). Applies everywhere similarity_threshold does -- both the initial
    # categorization fallback chain and the recategorization re-scan below, since
    # both share find_best_match.
    similarity_amount_ratio_tolerance: float = 4.0
    similarity_amount_absolute_floor: float = 5.0
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

    # Epic 8 (Recurring Payments): WR-16's due-date matching window -- a transaction
    # dated within this many days of a due-date instance is eligible to be matched
    # against that cycle.
    recurring_payment_match_window_days: int = 5
    # WR-18: the trust/tolerance auto-apply gate, reusing the same dual-gate shape
    # (ratio OR absolute floor) as similarity_amount_ratio_tolerance/_floor above,
    # via categorization.similarity.amounts_in_range -- deliberately tighter than
    # the categorization tolerance, since this gates an unreviewed write, not a
    # reviewable proposal.
    recurring_payment_trusted_amount_ratio_tolerance: float = 1.15
    recurring_payment_trusted_amount_absolute_floor: float = 5.0
    # WR-19: detection scan cadence and monthly-cadence pattern criteria.
    recurring_payment_detection_scan_interval_hours: int = 24
    recurring_payment_detection_min_occurrences: int = 2
    recurring_payment_detection_cadence_min_days: int = 25
    recurring_payment_detection_cadence_max_days: int = 35

    # Epic 9 (Local Embedding-Based Semantic Similarity): the vector DB is this
    # project's own docker-compose service (NFR Requirements) -- host/port have real
    # working defaults, unlike embedding_base_url below.
    qdrant_host: str = "vector-db"
    qdrant_port: int = 6333
    # No default -- entirely user-managed (NFR-5), unlike openrouter_base_url which
    # has a real hosted fallback. An empty string is treated identically to an
    # unreachable endpoint (WR-25 soft-fail), never a startup error.
    embedding_base_url: str = ""
    # Optional -- most local embedding servers don't require auth, but some (e.g. a
    # server also fronting OPENROUTER_BASE_URL with a key configured) do. Falls back
    # to openrouter_api_key when unset, since users pointing both URLs at the same
    # local server would otherwise have to duplicate the same key under two names.
    embedding_api_key: str = ""
    embedding_model: str = "embeddinggemma-300m"
    # Cosine similarity, 0.0-1.0 scale -- NOT the same scale as similarity_threshold
    # (0-100, fuzzy-text only). WR-23.
    # Matching Precision Refinement (WR-31): raised from the original Epic 9 default
    # of 0.75 -- a moderate +0.07 increase, one of three coordinated tightening
    # changes alongside the price-bucket text (below) and the LLM-agreement boost,
    # not expected to fully address over-eager matching on its own.
    embedding_similarity_threshold: float = 0.82
    embedding_top_k: int = 5
    embedding_batch_size: int = 50
    # Must match the embedding model's actual output dimensionality (used only when
    # creating the Qdrant collections, WR-26/NFR Requirements).
    embedding_dimensions: int = 768

    # Matching Precision Refinement: the LLM classification step now runs for every
    # transaction, always (WR-27) -- bounded concurrency (NFR-MPR-1) keeps a
    # multi-transaction file from firing an unbounded burst of concurrent requests
    # at the local model server.
    llm_classification_concurrency: int = 5
    # WR-27 (revised after live testing showed one-HTTP-call-per-transaction was
    # too many round-trips for a large statement): up to this many transactions'
    # descriptions are classified in a single prompt/response. Combined with
    # llm_classification_concurrency above, at most `concurrency` batches of this
    # size are in flight at once -- e.g. the defaults (5, 10) mean at most 50
    # transactions' worth of classification work in flight, via only 5 concurrent
    # HTTP requests, not 50.
    llm_classification_batch_size: int = 10
    # WR-29: ascending, comma-separated price bucket boundaries (SGD-equivalent
    # magnitude, sign-agnostic) appended to embedded text alongside the description/
    # name -- e.g. "1,5,10,20,50,100,200,500,1000,2000,5000" yields buckets like
    # "$0 to $1", "$1 to $5", ..., "$5000+". Env-tunable, not hardcoded (FR-MPR-5).
    embedding_price_bucket_boundaries: str = "1,5,10,20,50,100,200,500,1000,2000,5000"
    # WR-30: added to a candidate's raw cosine score (then capped at 1.0) when an
    # LLM-classification agreement signal is present, before the threshold check
    # above -- never a penalty on disagreement, only a boost withheld.
    embedding_llm_agreement_boost: float = 0.05

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
        """WR-33: the settings-override file takes the HIGHEST precedence -- checked
        before process env, not after. pydantic-settings' default order (init > env >
        dotenv > secrets) would otherwise make this file permanently ineffective for
        every setting docker-compose.yml already maps as a process env var --
        confirmed empirically before writing this (see
        aidlc-docs/construction/ingestion-worker/functional-design/business-rules.md
        WR-33). A missing file (e.g. before any setting has ever been changed via the
        Settings page) is not an error -- DotEnvSettingsSource tolerates a nonexistent
        env_file path, confirmed the same way.
        """
        override_source = DotEnvSettingsSource(settings_cls, env_file=SETTINGS_OVERRIDE_FILE)
        return (override_source, init_settings, env_settings, dotenv_settings, file_secret_settings)


settings = Settings()
