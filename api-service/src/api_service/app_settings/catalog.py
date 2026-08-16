"""The settings allow-list (AR-28) -- the sole source of truth for which of the 40
in-scope settings exist and what a valid value looks like. A name not in this dict
has no code path to a value, secret or otherwise (NFR-CAS-2).

`owning_services` is a tuple, not a single value, because exactly one setting
(`gemini_model`) is read by both backend services from the same shared override file
(Application Design's single-shared-file decision) -- found while building this
catalog, not anticipated at Application Design, so `getRestartGuidance` (service.py)
returns one restart target per owning service, not always exactly one (AR-30, revised
in place here to generalize from "a single command" to "one command per affected
service").

`category` groups settings the same way `.env.example`'s own section comments
already do (Matching & Categorization / Embedding & Semantic Matching / Recurring
Payments / Backup / Ingestion / API & Access / Ask AI) -- the Settings page groups by
this instead of only Standard/Advanced, so a user can find "all the recurring
payments tuning" together the same way they already can in `.env.example`.

`description` is drawn directly from that same `.env.example`/config.py explanatory
comment for each field -- not a generic label. Where `.env.example` didn't have a
comment (an oversight fixed here, not perpetuated), the description matches the
reasoning already documented in Ingestion Worker's `business-rules.md`/`config.py`.

`default` is a fallback of last resort only (used if the live `Settings` object
somehow lacks the attribute, which should never happen -- see below). It is NOT the
primary source for a setting's displayed value: `service.py`'s
`_effective_value_str` reads the live, already-constructed `config.settings` object
first (override file, else whatever docker-compose/.env actually supplied, else the
built-in default -- exactly the real effective value the owning service itself would
use). This was a real bug in the original version of this catalog (found from user
feedback after Build and Test): OPENROUTER_MODEL was reported as "openrouter/free"
(hardcoded default) even when the real deployment had it set to
"gemma-4-26b-a4b-it-4bit" via `.env`. Fixed by giving api-service its own
display-only mirror of every Ingestion-Worker-owned field (config.py's "Display-only
mirror" block) fed the identical docker-compose env vars Ingestion Worker itself
gets, so both services' `Settings` objects agree by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transactagent_db.models import SettingOwningService

_WORKER = SettingOwningService.INGESTION_WORKER
_API = SettingOwningService.API_SERVICE


@dataclass(frozen=True)
class SettingSpec:
    name: str
    owning_services: tuple[SettingOwningService, ...]
    classification: str  # "standard" | "advanced"
    category: str
    description: str
    type: str  # "float" | "int" | "string" | "enum"
    default: Any
    min: float | None = None
    max: float | None = None
    min_exclusive: bool = False
    allowed_values: tuple[str, ...] | None = None
    format: str | None = None  # "currency_code" | "url" | "url_or_empty" | "url_list" | "ascending_number_list" | "non_empty"
    cross_field: str | None = None  # "less_than" | "greater_than" | "less_or_equal" | "greater_or_equal"
    cross_field_partner: str | None = None


_MATCHING = "Matching & Categorization"
_EMBEDDING = "Embedding & Semantic Matching"
_RECURRING = "Recurring Payments"
_BACKUP = "Backup"
_INGESTION = "Ingestion"
_API_ACCESS = "API & Access"
_ASK_AI = "Ask AI"

_SPECS: tuple[SettingSpec, ...] = (
    # --- Matching & Categorization ---
    SettingSpec(
        "similarity_threshold", (_WORKER,), "standard", _MATCHING,
        "Fuzzy-text match score (0-100) a candidate transaction must reach to be treated as the same payee during categorization.",
        "float", 85.0, min=0.0, max=100.0,
    ),
    SettingSpec(
        "similarity_amount_ratio_tolerance", (_WORKER,), "standard", _MATCHING,
        "A same-merchant text match is only accepted if the two amounts are within this ratio of each other (or within the absolute floor below) -- guards against unrelated payments made through the same bill-pay kiosk being merged.",
        "float", 4.0, min=1.0,
    ),
    SettingSpec(
        "similarity_amount_absolute_floor", (_WORKER,), "standard", _MATCHING,
        "Small-value alternative to the ratio tolerance above -- handles cases like two currency-conversion fees of $0.01 and $0.27, where a ratio comparison alone would be too strict.",
        "float", 5.0, min=0.0,
    ),
    SettingSpec(
        "recategorization_auto_apply_threshold", (_WORKER,), "standard", _MATCHING,
        "Similarity score above which the retroactive re-scan (triggered by a manual correction) auto-applies a category with no human review, instead of creating a reviewable proposal.",
        "float", 97.0, min=0.0, max=100.0,
    ),
    SettingSpec(
        "extraction_confidence_threshold", (_WORKER,), "standard", _MATCHING,
        "Minimum confidence the statement-extraction step requires before treating an extracted transaction as reliable.",
        "enum", "medium", allowed_values=("low", "medium", "high"),
    ),
    SettingSpec(
        "llm_classification_batch_size", (_WORKER,), "standard", _MATCHING,
        "How many transaction descriptions are classified together in a single prompt/response to the categorization LLM, instead of one call per transaction.",
        "int", 10, min=1,
    ),
    SettingSpec(
        "llm_classification_concurrency", (_WORKER,), "standard", _MATCHING,
        "Maximum number of concurrent categorization-LLM requests in flight at once, across all batches.",
        "int", 5, min=1,
    ),
    SettingSpec(
        "openrouter_base_url", (_WORKER,), "advanced", _MATCHING,
        "OpenAI-compatible endpoint used for transaction categorization -- OpenRouter's hosted API by default, or your own local model server (e.g. via host.docker.internal).",
        "string", "https://openrouter.ai/api/v1", format="url",
    ),
    SettingSpec(
        "openrouter_model", (_WORKER,), "advanced", _MATCHING,
        "The model your categorization endpoint actually serves -- e.g. a specific local model name when openrouter_base_url points at your own server.",
        "string", "openrouter/free", format="non_empty",
    ),
    SettingSpec(
        "gemini_model", (_WORKER, _API), "advanced", _MATCHING,
        "Model used for statement-image extraction (Ingestion Worker) and the Ask AI feature (API Service) -- shared by both, must support image input.",
        "string", "gemini-3.5-flash-lite", format="non_empty",
    ),
    # --- Embedding & Semantic Matching ---
    SettingSpec(
        "embedding_similarity_threshold", (_WORKER,), "standard", _EMBEDDING,
        "Cosine similarity (0.0-1.0 scale -- NOT the same scale as similarity_threshold above) an embedding-based match must reach to be accepted.",
        "float", 0.82, min=0.0, max=1.0,
    ),
    SettingSpec(
        "embedding_top_k", (_WORKER,), "standard", _EMBEDDING,
        "Number of nearest-neighbor candidates fetched from the vector store per embedding query.",
        "int", 5, min=1,
    ),
    SettingSpec(
        "embedding_batch_size", (_WORKER,), "standard", _EMBEDDING,
        "How many pending transactions/recurring payments get their embedding computed per background poll cycle.",
        "int", 50, min=1,
    ),
    SettingSpec(
        "embedding_price_bucket_boundaries", (_WORKER,), "standard", _EMBEDDING,
        "Ascending, comma-separated price-range boundaries appended to embedded text, e.g. \"1,5,10\" yields buckets like $0-$1, $1-$5, $5-$10, $10+.",
        "string", "1,5,10,20,50,100,200,500,1000,2000,5000", format="ascending_number_list",
    ),
    SettingSpec(
        "embedding_llm_agreement_boost", (_WORKER,), "standard", _EMBEDDING,
        "Score boost added to a candidate's raw cosine score when the LLM's own classification agrees with the candidate's category -- never a penalty on disagreement, only a boost withheld.",
        "float", 0.05, min=0.0,
    ),
    SettingSpec(
        "embedding_base_url", (_WORKER,), "advanced", _EMBEDDING,
        "Your local embedding model server's endpoint. Leave empty to disable embedding-based matching entirely -- falls back to fuzzy-text matching only, with no error.",
        "string", "", format="url_or_empty",
    ),
    SettingSpec(
        "embedding_model", (_WORKER,), "advanced", _EMBEDDING,
        "Model name your embedding server is actually running -- must match embedding_dimensions below.",
        "string", "embeddinggemma-300m", format="non_empty",
    ),
    SettingSpec(
        "embedding_dimensions", (_WORKER,), "advanced", _EMBEDDING,
        "Output vector size of your embedding model -- must match it exactly; used when creating the Qdrant collections.",
        "int", 768, min=1,
    ),
    SettingSpec(
        "qdrant_host", (_WORKER,), "advanced", _EMBEDDING,
        "Internal docker-network address of the vector database service -- rarely needs changing in a single-compose deployment.",
        "string", "vector-db", format="non_empty",
    ),
    SettingSpec(
        "qdrant_port", (_WORKER,), "advanced", _EMBEDDING,
        "Internal docker-network port of the vector database service -- rarely needs changing in a single-compose deployment.",
        "int", 6333, min=1, max=65535,
    ),
    # --- Recurring Payments ---
    SettingSpec(
        "recurring_payment_match_window_days", (_WORKER,), "standard", _RECURRING,
        "A transaction dated within this many days of a due-date instance is eligible to be matched against that cycle.",
        "int", 5, min=0,
    ),
    SettingSpec(
        "recurring_payment_trusted_amount_ratio_tolerance", (_WORKER,), "standard", _RECURRING,
        "For a trusted recurring payment, the amount tolerance (as a ratio) allowed before a match needs manual review instead of auto-applying.",
        "float", 1.15, min=1.0,
    ),
    SettingSpec(
        "recurring_payment_trusted_amount_absolute_floor", (_WORKER,), "standard", _RECURRING,
        "Small-value alternative to the ratio tolerance above, for trusted recurring-payment matching.",
        "float", 5.0, min=0.0,
    ),
    SettingSpec(
        "recurring_payment_detection_scan_interval_hours", (_WORKER,), "standard", _RECURRING,
        "How often the background scan looks through transaction history for untracked recurring charges.",
        "int", 24, min=0, min_exclusive=True,
    ),
    SettingSpec(
        "recurring_payment_detection_min_occurrences", (_WORKER,), "standard", _RECURRING,
        "Minimum number of similar past charges required before a pattern is suggested as a recurring payment.",
        "int", 2, min=2,
    ),
    SettingSpec(
        "recurring_payment_detection_cadence_min_days", (_WORKER,), "standard", _RECURRING,
        "Lower bound (days between occurrences) for a pattern to be considered monthly-cadence recurring -- must stay below the max below.",
        "int", 25, min=0, min_exclusive=True,
        cross_field="less_than", cross_field_partner="recurring_payment_detection_cadence_max_days",
    ),
    SettingSpec(
        "recurring_payment_detection_cadence_max_days", (_WORKER,), "standard", _RECURRING,
        "Upper bound (days between occurrences) for a pattern to be considered monthly-cadence recurring -- must stay above the min above.",
        "int", 35, min=0, min_exclusive=True,
        cross_field="greater_than", cross_field_partner="recurring_payment_detection_cadence_min_days",
    ),
    SettingSpec(
        "recurring_payment_due_soon_lead_days", (_API,), "standard", _RECURRING,
        "How many days before an upcoming due date (or before the next cycle, once the current one is paid) a recurring payment's status flips to \"due soon\".",
        "int", 5, min=0,
    ),
    # --- Backup ---
    SettingSpec(
        "backup_schedule_hour", (_WORKER,), "standard", _BACKUP,
        "Hour of the day (server/container local time, 0-23) the nightly transaction backup runs.",
        "int", 2, min=0, max=23,
    ),
    SettingSpec(
        "backup_retention_count", (_WORKER,), "standard", _BACKUP,
        "Number of most-recent backup files kept in the Drive backup folder before older ones are deleted.",
        "int", 7, min=1,
    ),
    # --- Ingestion ---
    SettingSpec(
        "poll_interval_seconds", (_WORKER,), "standard", _INGESTION,
        "How often the Ingestion Worker checks for a new ingestion run, recategorization job, due backup, due detection scan, or pending embedding batch.",
        "float", 5.0, min=0.0, min_exclusive=True,
    ),
    SettingSpec(
        "retry_max_attempts", (_WORKER,), "standard", _INGESTION,
        "Maximum retry attempts for transient failures (Drive/LLM calls) before giving up on a file.",
        "int", 3, min=0,
    ),
    SettingSpec(
        "retry_backoff_base_seconds", (_WORKER,), "standard", _INGESTION,
        "Base delay for exponential backoff between retry attempts.",
        "float", 2.0, min=0.0, min_exclusive=True,
    ),
    SettingSpec(
        "reporting_currency", (_WORKER,), "standard", _INGESTION,
        "The currency every transaction's converted amount is reported in across dashboards and exports.",
        "string", "SGD", format="currency_code",
    ),
    # --- API & Access ---
    SettingSpec(
        "jwt_expiry_minutes", (_API,), "standard", _API_ACCESS,
        "How long a login session stays valid before requiring re-authentication.",
        "int", 1440, min=1,
    ),
    SettingSpec(
        "default_page_size", (_API,), "standard", _API_ACCESS,
        "Default number of rows returned per page for list endpoints -- must stay less than or equal to max_page_size below.",
        "int", 50, min=1,
        cross_field="less_or_equal", cross_field_partner="max_page_size",
    ),
    SettingSpec(
        "max_page_size", (_API,), "standard", _API_ACCESS,
        "Maximum rows a client can request per page -- must stay greater than or equal to default_page_size above.",
        "int", 200, min=1,
        cross_field="greater_or_equal", cross_field_partner="default_page_size",
    ),
    SettingSpec(
        "csv_export_max_rows", (_API,), "standard", _API_ACCESS,
        "Maximum rows allowed in a single CSV export.",
        "int", 50_000, min=1,
    ),
    SettingSpec(
        "frontend_origin", (_API,), "advanced", _API_ACCESS,
        "Comma-separated list of origins allowed to call the API (CORS) -- each must exactly match an address you actually load the frontend from, including port. A wrong value can lock this app's own UI out of the API.",
        "string", "http://localhost:8787", format="url_list",
    ),
    SettingSpec(
        "google_oauth_redirect_uri", (_API,), "advanced", _API_ACCESS,
        "Must exactly match the redirect URI registered in your Google OAuth client, or Drive connect breaks.",
        "string", "http://localhost:7878/drive/callback", format="url",
    ),
    # --- Ask AI ---
    SettingSpec(
        "ai_assistant_max_transactions", (_API,), "standard", _ASK_AI,
        "Caps how many transactions are sent as context per Ask AI question, most recent first -- keeps a very large or \"all transactions\" question from producing an unbounded prompt as your data grows.",
        "int", 3000, min=1,
    ),
)

SETTINGS_BY_NAME: dict[str, SettingSpec] = {spec.name: spec for spec in _SPECS}

# Correction (2026-08-16, found while adding category/description fields after user
# feedback on Build and Test): ai_assistant_max_transactions was in the original
# Requirements "Expose" list (FR-CAS-1's source table) but was missing from both this
# catalog and AR-28's table -- a real omission from the original 40-setting count,
# not a duplicate of the earlier 35->40 correction. True count is 41. See
# `configurable-app-settings-requirements.md`'s second Post-Approval Change section.
assert len(SETTINGS_BY_NAME) == 41, f"expected 41 settings, got {len(SETTINGS_BY_NAME)}"
