# Configurable Application Settings — Clarifying Questions

Context for these questions (current behavior, confirmed by reading the code):

- `api-service/src/api_service/config.py` and `ingestion-worker/src/ingestion_worker/config.py` are both `pydantic_settings.BaseSettings` subclasses with `env_prefix=""` and **no `env_file` configured** — they read purely from process environment variables. The root `.env` file is only ever read by **docker-compose itself**, to substitute `${VAR}` into each service's `environment:` block at container-creation time. The Python apps never read `.env` directly.
- Both `Settings` objects are instantiated once, at module import time (`settings = Settings()`), and never re-read afterward. **Every setting requires a container restart to pick up a new value** — there is no in-process hot-reload today, for any setting.
- `docker-compose.yml`'s `ingestion-worker` service is **missing explicit `environment:` mappings for many settings that already exist** in `config.py`/`.env.example` (e.g. `SIMILARITY_THRESHOLD`, `POLL_INTERVAL_SECONDS`, `LLM_CLASSIFICATION_BATCH_SIZE`/`CONCURRENCY`, `RECATEGORIZATION_AUTO_APPLY_THRESHOLD`, all `RECURRING_PAYMENT_*` vars, `RETRY_*`, `REPORTING_CURRENCY`, `EXTRACTION_CONFIDENCE_THRESHOLD`). Those settings currently always use their Python-side hardcoded default, regardless of what's in `.env`. **This gap will need to be closed for any of them to become genuinely editable**, independent of which other answers below are chosen.
- No Docker-socket, `subprocess`, or container-orchestration code exists anywhere in the codebase today — a restart mechanism is a from-scratch architecture decision, not an extension of something already there.
- A plain `docker restart <container>` reuses the container's existing environment (fixed at the time `docker compose up` created it) — it does **not** re-read `.env` or the compose file. Only `docker compose up -d <service>` (recreate) re-evaluates `environment:`. This distinction matters for both the reload mechanism (Question 4) and how privileged the restart trigger needs to be (Question 2/3).
- The existing Settings page (`frontend/src/pages/SettingsPage.tsx`) has two sections today: a Google Drive connection card and category management (add/rename/remove), using TanStack Query + Radix `Dialog` for confirmations. All API routes (including this page's) sit behind the project's single-user JWT auth.

## Proposed Settings Classification

Every setting currently in either `config.py`, classified by proposed exposure:

**Expose (safe, operationally tunable)**

| Setting | Service | Type | Notes |
|---|---|---|---|
| `similarity_threshold` | Worker | float 0-100 | fuzzy-text match cutoff |
| `similarity_amount_ratio_tolerance` | Worker | float | |
| `similarity_amount_absolute_floor` | Worker | float | |
| `recategorization_auto_apply_threshold` | Worker | float 0-100 | |
| `extraction_confidence_threshold` | Worker | enum low/medium/high | |
| `poll_interval_seconds` | Worker | float | |
| `retry_max_attempts` | Worker | int | |
| `retry_backoff_base_seconds` | Worker | float | |
| `reporting_currency` | Worker | str (currency code) | |
| `recurring_payment_match_window_days` | Worker | int | |
| `recurring_payment_trusted_amount_ratio_tolerance` | Worker | float | |
| `recurring_payment_trusted_amount_absolute_floor` | Worker | float | |
| `recurring_payment_detection_scan_interval_hours` | Worker | int | |
| `recurring_payment_detection_min_occurrences` | Worker | int | |
| `recurring_payment_detection_cadence_min_days` / `_max_days` | Worker | int | |
| `embedding_similarity_threshold` | Worker | float 0-1 | |
| `embedding_top_k` | Worker | int | |
| `embedding_batch_size` | Worker | int | |
| `embedding_price_bucket_boundaries` | Worker | str (csv) | |
| `embedding_llm_agreement_boost` | Worker | float | |
| `llm_classification_batch_size` | Worker | int | |
| `llm_classification_concurrency` | Worker | int | |
| `backup_schedule_hour` | Worker | int 0-23 | |
| `backup_retention_count` | Worker | int | |
| `jwt_expiry_minutes` | API | int | session length |
| `default_page_size` / `max_page_size` | API | int | |
| `csv_export_max_rows` | API | int | |
| `ai_assistant_max_transactions` | API | int | |
| `recurring_payment_due_soon_lead_days` | API | int | |

**Advanced / needs discussion (safe from a secrecy standpoint, but risky to change carelessly)**

| Setting | Service | Risk |
|---|---|---|
| `embedding_base_url` | Worker | user's own local-model endpoint — legitimately useful to edit, but a typo silently disables embedding matching (soft-fail, no error) |
| `embedding_model` / `embedding_dimensions` | Worker | must match the actual model serving `embedding_base_url`; mismatch breaks the Qdrant collections |
| `openrouter_base_url` / `openrouter_model` | Worker | same category as above, for the classification LLM |
| `gemini_model` | Worker + API | shared between both services |
| `frontend_origin` | API | CORS allow-list — a bad value can lock the admin UI itself out of the API |
| `google_oauth_redirect_uri` | API | must exactly match the URI registered in Google's OAuth console; mismatch breaks Drive connect |
| `qdrant_host` / `qdrant_port` | Worker | internal docker-network address; no real reason to change in a single-compose deployment |

**Exclude (secrets/credentials — must never be exposed)**

`db_user`, `db_password`, `db_host`, `db_port`, `db_name`, `jwt_secret`, `jwt_algorithm`, `gemini_api_key`, `openrouter_api_key`, `embedding_api_key`, `google_oauth_client_id`, `google_oauth_client_secret`, `google_drive_folder_id`, `google_drive_backup_folder_id` (Drive folder IDs aren't credentials, but identify the user's personal Drive layout — proposed excluded as low-value/personal rather than operational).

---

Please answer each question below by filling in the letter after `[Answer]:`. If none of the options fit, choose "Other" and describe your preference.

## Question 1
Which settings should actually ship in v1 of the Settings page?

A) The full "Expose" table above (28 settings) — the broadest useful set

B) Just the 7 settings you originally named (`embedding_similarity_threshold`, `llm_classification_batch_size`, `llm_classification_concurrency`, `embedding_price_bucket_boundaries`, `embedding_llm_agreement_boost`, `similarity_threshold`, `poll_interval_seconds`) — smallest, fastest to ship, everything else stays `.env`-only for now

C) The full "Expose" table, PLUS the "Advanced" table too (with clear UI warnings on the advanced ones) — most complete, most risk of user-caused breakage

D) Other (please describe after [Answer]: tag below — e.g. list specific additions/removals from the "Expose" table)

[Answer]: C 

## Question 2
Where should the Docker restart capability live?

A) A small, dedicated "supervisor" sidecar container whose only job is holding Docker-socket access and restarting the two app containers on request — api-service calls it over an internal-only endpoint, so the socket itself is never reachable from the internet-facing api-service process

B) Mount the Docker socket directly into api-service itself — fewer moving parts, but api-service (already internet-facing, already handling arbitrary user input) gains a capability equivalent to root on the Docker host

C) No automated restart at all for v1 — saving a setting writes the config change and shows a "Restart required" banner with the exact command to run (e.g. `docker compose up -d ingestion-worker`); the user restarts manually

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 3
How should a saved setting actually reach the target container's process environment?

A) A new, separate, non-secret override file (e.g. `config/runtime-overrides.env`, git-ignored) that both `Settings` classes load via pydantic's `env_file` support, layered under the real `.env`/compose-provided values. Restart only needs a plain `docker restart <container>` (the file is already on the container's mounted filesystem, re-read at process start) — no compose recreate, no re-evaluation of the compose file needed.

B) Write directly to the root `.env` file. Restart must be a full `docker compose up -d <service>` (recreate), since only that path re-evaluates `${VAR}` substitution into the container's environment — a plain `docker restart` would not pick up the change.

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
`ingestion-worker` runs a continuous poll loop that may be mid-cycle (e.g. actively processing a bank statement) when a restart is requested. Should the restart:

A) Happen immediately regardless — the poll loop's existing retry/resume design (it re-scans on the next cycle) already tolerates being interrupted mid-file, so an immediate restart is safe

B) Wait for the current poll cycle to finish (a short grace period) before restarting, to avoid interrupting an in-flight statement import

C) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 5
Where should this live in the Settings page?

A) A new section on the existing `SettingsPage.tsx`, below Categories — one page, consistent with how Drive Connection and Categories already coexist there

B) A new, separate page/tab (e.g. "Configuration"), reached from the nav — keeps the existing Settings page focused on user-level preferences vs. this being closer to ops/admin configuration

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
How strict should input validation be?

A) Strict — reuse each setting's real type/range from `config.py` (e.g. `embedding_similarity_threshold` must be 0.0–1.0, thresholds can't be negative, `backup_schedule_hour` must be 0–23) and reject invalid values before writing or restarting

B) Minimal — basic type checking only (e.g. "must be a number"), defer stricter per-field range validation to a follow-up

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 7
Should changes be tracked with a history (old value, new value, who, when)?

A) Yes — persist a change history (new small table), visible somewhere in the UI (even just a simple list) — useful for "why did matching behavior change" debugging later

B) No — just apply the new value directly, no history for v1

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 8
Should saving a setting require anything beyond the app's existing JWT auth (the same auth already protecting every other route, including today's category add/rename/remove)?

A) Same JWT auth as everything else — no extra step, consistent with how category management already works

B) An extra confirmation step for settings changes specifically (e.g. a "this will restart a service" confirmation dialog, distinct from just being logged in) — given a bad value can degrade categorization/matching accuracy or (per Question 2) restart a running container

C) Other (please describe after [Answer]: tag below)

[Answer]: B
