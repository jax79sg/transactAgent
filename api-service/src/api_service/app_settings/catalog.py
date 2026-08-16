"""The settings allow-list (AR-28) -- the sole source of truth for which of the 35
in-scope settings exist and what a valid value looks like. A name not in this dict
has no code path to a value, secret or otherwise (NFR-CAS-2).

`owning_services` is a tuple, not a single value, because exactly one setting
(`gemini_model`) is read by both backend services from the same shared override file
(Application Design's single-shared-file decision) -- found while building this
catalog, not anticipated at Application Design, so `getRestartGuidance` (service.py)
returns one restart target per owning service, not always exactly one (AR-30, revised
in place here to generalize from "a single command" to "one command per affected
service").

`default` mirrors each field's actual Python-side default in the owning service's own
config.py, as of this feature's Code Generation -- kept here, not read live from the
other service's process, since API Service has no way to introspect
Ingestion Worker's live config directly (separate container, separate process,
no shared-DB-only-coordination rule violation intended). Known limitation, documented
rather than hidden: for a worker-owned setting a deployment already customized via
root `.env` directly (the pre-existing mechanism, before this feature existed) rather
than through this feature's override file, `getSetting`'s displayed value is this
catalog's built-in default, not that `.env` value, until the user overrides it once
through the Settings page -- at which point display becomes accurate going forward,
since the override file is the one channel both services genuinely share.
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
    type: str  # "float" | "int" | "string" | "enum"
    default: Any
    min: float | None = None
    max: float | None = None
    min_exclusive: bool = False
    allowed_values: tuple[str, ...] | None = None
    format: str | None = None  # "currency_code" | "url" | "url_or_empty" | "url_list" | "ascending_number_list" | "non_empty"
    cross_field: str | None = None  # "less_than" | "greater_than" | "less_or_equal" | "greater_or_equal"
    cross_field_partner: str | None = None


_SPECS: tuple[SettingSpec, ...] = (
    # --- Ingestion Worker, standard (AR-28) ---
    SettingSpec("similarity_threshold", (_WORKER,), "standard", "float", 85.0, min=0.0, max=100.0),
    SettingSpec("similarity_amount_ratio_tolerance", (_WORKER,), "standard", "float", 4.0, min=1.0),
    SettingSpec("similarity_amount_absolute_floor", (_WORKER,), "standard", "float", 5.0, min=0.0),
    SettingSpec("recategorization_auto_apply_threshold", (_WORKER,), "standard", "float", 97.0, min=0.0, max=100.0),
    SettingSpec(
        "extraction_confidence_threshold", (_WORKER,), "standard", "enum", "medium",
        allowed_values=("low", "medium", "high"),
    ),
    SettingSpec("poll_interval_seconds", (_WORKER,), "standard", "float", 5.0, min=0.0, min_exclusive=True),
    SettingSpec("retry_max_attempts", (_WORKER,), "standard", "int", 3, min=0),
    SettingSpec("retry_backoff_base_seconds", (_WORKER,), "standard", "float", 2.0, min=0.0, min_exclusive=True),
    SettingSpec("reporting_currency", (_WORKER,), "standard", "string", "SGD", format="currency_code"),
    SettingSpec("recurring_payment_match_window_days", (_WORKER,), "standard", "int", 5, min=0),
    SettingSpec("recurring_payment_trusted_amount_ratio_tolerance", (_WORKER,), "standard", "float", 1.15, min=1.0),
    SettingSpec("recurring_payment_trusted_amount_absolute_floor", (_WORKER,), "standard", "float", 5.0, min=0.0),
    SettingSpec(
        "recurring_payment_detection_scan_interval_hours", (_WORKER,), "standard", "int", 24,
        min=0, min_exclusive=True,
    ),
    SettingSpec("recurring_payment_detection_min_occurrences", (_WORKER,), "standard", "int", 2, min=2),
    SettingSpec(
        "recurring_payment_detection_cadence_min_days", (_WORKER,), "standard", "int", 25,
        min=0, min_exclusive=True,
        cross_field="less_than", cross_field_partner="recurring_payment_detection_cadence_max_days",
    ),
    SettingSpec(
        "recurring_payment_detection_cadence_max_days", (_WORKER,), "standard", "int", 35,
        min=0, min_exclusive=True,
        cross_field="greater_than", cross_field_partner="recurring_payment_detection_cadence_min_days",
    ),
    SettingSpec("embedding_similarity_threshold", (_WORKER,), "standard", "float", 0.82, min=0.0, max=1.0),
    SettingSpec("embedding_top_k", (_WORKER,), "standard", "int", 5, min=1),
    SettingSpec("embedding_batch_size", (_WORKER,), "standard", "int", 50, min=1),
    SettingSpec(
        "embedding_price_bucket_boundaries", (_WORKER,), "standard", "string",
        "1,5,10,20,50,100,200,500,1000,2000,5000", format="ascending_number_list",
    ),
    SettingSpec("embedding_llm_agreement_boost", (_WORKER,), "standard", "float", 0.05, min=0.0),
    SettingSpec("llm_classification_batch_size", (_WORKER,), "standard", "int", 10, min=1),
    SettingSpec("llm_classification_concurrency", (_WORKER,), "standard", "int", 5, min=1),
    SettingSpec("backup_schedule_hour", (_WORKER,), "standard", "int", 2, min=0, max=23),
    SettingSpec("backup_retention_count", (_WORKER,), "standard", "int", 7, min=1),
    # --- Ingestion Worker, advanced (AR-28) ---
    SettingSpec("embedding_base_url", (_WORKER,), "advanced", "string", "", format="url_or_empty"),
    SettingSpec("embedding_model", (_WORKER,), "advanced", "string", "embeddinggemma-300m", format="non_empty"),
    SettingSpec("embedding_dimensions", (_WORKER,), "advanced", "int", 768, min=1),
    SettingSpec("openrouter_base_url", (_WORKER,), "advanced", "string", "https://openrouter.ai/api/v1", format="url"),
    SettingSpec("openrouter_model", (_WORKER,), "advanced", "string", "openrouter/free", format="non_empty"),
    SettingSpec("qdrant_host", (_WORKER,), "advanced", "string", "vector-db", format="non_empty"),
    SettingSpec("qdrant_port", (_WORKER,), "advanced", "int", 6333, min=1, max=65535),
    # Shared by both services -- see module docstring.
    SettingSpec("gemini_model", (_WORKER, _API), "advanced", "string", "gemini-3.5-flash-lite", format="non_empty"),
    # --- API Service, standard (AR-28) ---
    SettingSpec("jwt_expiry_minutes", (_API,), "standard", "int", 1440, min=1),
    SettingSpec(
        "default_page_size", (_API,), "standard", "int", 50, min=1,
        cross_field="less_or_equal", cross_field_partner="max_page_size",
    ),
    SettingSpec(
        "max_page_size", (_API,), "standard", "int", 200, min=1,
        cross_field="greater_or_equal", cross_field_partner="default_page_size",
    ),
    SettingSpec("csv_export_max_rows", (_API,), "standard", "int", 50_000, min=1),
    SettingSpec("recurring_payment_due_soon_lead_days", (_API,), "standard", "int", 5, min=0),
    # --- API Service, advanced (AR-28) ---
    SettingSpec("frontend_origin", (_API,), "advanced", "string", "http://localhost:8787", format="url_list"),
    SettingSpec(
        "google_oauth_redirect_uri", (_API,), "advanced", "string",
        "http://localhost:7878/drive/callback", format="url",
    ),
)

SETTINGS_BY_NAME: dict[str, SettingSpec] = {spec.name: spec for spec in _SPECS}

# Correction (2026-08-16, found while building this catalog against the real
# config.py fields): Requirements/Application Design/Database Functional Design all
# said "35 settings" -- an undercount, traced to two rows in the original
# classification tables (`configurable-app-settings-questions.md`) that each named
# TWO settings separated by "/" (`recurring_payment_detection_cadence_min_days /
# _max_days`, `default_page_size / max_page_size`, `embedding_model /
# embedding_dimensions`, `qdrant_host / qdrant_port`) but were counted as one row
# each. The real, authoritative count -- every distinct field name actually present
# in both services' config.py, which is exactly what this catalog enumerates -- is
# 40. AR-28 (business-rules.md) already listed all 40 individually and was correct;
# only the summary count elsewhere was wrong. See
# `configurable-app-settings-requirements.md`'s "Post-Approval Change" section.
assert len(SETTINGS_BY_NAME) == 40, f"expected 40 settings, got {len(SETTINGS_BY_NAME)}"
