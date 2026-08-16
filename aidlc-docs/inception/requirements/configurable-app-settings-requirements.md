# Requirements: Configurable Application Settings

## Intent Analysis

- **User request**: "Follow this project's AI-DLC workflow to scope and build a new feature: expose non-sensitive application settings (currently only in `.env` / `ingestion-worker`'s `config.py`, `api-service`'s `config.py`) in the Frontend's Settings page, editable by the user, with a restart-on-change option where needed." Explicitly deferred out of the Matching Precision Refinement feature's Build and Test stage (see `matching-precision-refinement-build-and-test-summary.md` and `audit.md`) because it needs its own security/architecture decisions: which settings are safe to expose, a real config-write + restart mechanism, and a Docker-socket access decision.
- **Request type**: New Feature — a new, self-contained runtime-configuration capability layered across all 4 units (Database for change history, Ingestion Worker + API Service for settings read/write, Frontend for the UI).
- **Scope estimate**: Multiple components — new API surface + validation + change-history persistence (API Service), a settings-loading mechanism change in both backend services (Ingestion Worker + API Service `config.py`), a `docker-compose.yml` fix to close a pre-existing env-passthrough gap, and a new UI section (Frontend).
- **Complexity estimate**: Moderate-to-Complex — no new external dependency or unfamiliar tech, but a genuine architecture decision (how a running container picks up a changed, file-backed setting without Docker-socket access) and a real security boundary (secrets must never become writable through this new surface) that didn't exist in any prior feature.

## Current Behavior (baseline, confirmed against live code — see audit.md)

- `api-service/src/api_service/config.py` and `ingestion-worker/src/ingestion_worker/config.py` are `pydantic_settings.BaseSettings` subclasses with no `env_file` configured — they read only from process environment variables, set once by `docker-compose.yml`'s `environment:` block at container-creation time. The root `.env` file is read only by docker-compose itself, never by the Python apps directly.
- Both `Settings` objects are instantiated once, at module import (`settings = Settings()`), and never re-read — every setting change requires a container restart to take effect.
- `docker-compose.yml`'s `ingestion-worker.environment:` block does not map many settings that already exist in `config.py`/`.env.example` (e.g. `SIMILARITY_THRESHOLD`, `POLL_INTERVAL_SECONDS`, `LLM_CLASSIFICATION_BATCH_SIZE`/`CONCURRENCY`, `RECATEGORIZATION_AUTO_APPLY_THRESHOLD`, all `RECURRING_PAYMENT_*` vars, `RETRY_*`, `REPORTING_CURRENCY`, `EXTRACTION_CONFIDENCE_THRESHOLD`) — those settings currently always use their Python-side hardcoded default regardless of `.env`.
- No Docker-socket, `subprocess`, or container-orchestration code exists anywhere in the codebase (confirmed via grep) — a restart mechanism is a from-scratch decision.
- A plain `docker restart <container>` reuses the container's existing environment (fixed when `docker compose up` created it); it does not re-read `.env`/the compose file. Only `docker compose up -d <service>` (recreate) re-evaluates `environment:`.
- The existing `SettingsPage.tsx` has two sections (Google Drive connection, category management), using TanStack Query + Radix `Dialog`, behind the project's single-user JWT auth.
- `ingestion-worker` reports liveness via a heartbeat file (`/tmp/worker-heartbeat`, touched periodically), used today only by its own Docker healthcheck.

## Resolved Decisions (from clarifying questions)

| # | Decision | Answer |
|---|---|---|
| 1 | Settings scope for v1 | Both the proposed "Expose" table (28 settings) AND the "Advanced" table (7 settings: `embedding_base_url`, `embedding_model`, `embedding_dimensions`, `openrouter_base_url`, `openrouter_model`, `gemini_model`, `frontend_origin`, `google_oauth_redirect_uri`, `qdrant_host`, `qdrant_port`) ship together — 35 settings total, with the Advanced ones visually flagged as riskier to change. |
| 2 | Restart-trigger architecture | No automation, no Docker-socket access anywhere in this feature. Saving a setting shows a "Restart required" indicator with the exact manual command to run; the human runs it. |
| 3 | Persistence/reload mechanism | A new, separate, non-secret override file (not the secrets-bearing root `.env`), loaded by both `Settings` classes via pydantic's `env_file` support. Because restart is manual and file-based (Decision 2), a plain `docker restart <container>` is sufficient — no compose recreate needed. |
| 4/Clarification 1 | Ingestion Worker restart timing guidance | The Settings page SHALL show a live worker busy/idle indicator (heartbeat-based); the "safe to restart" state is only shown once the worker is confirmed idle — while busy, it says so instead of presenting the restart command as ready. |
| 5 | Settings page placement | A new section on the existing `SettingsPage.tsx`, below Categories — not a separate page. |
| 6 | Validation strictness | Strict — each setting's real type/range (as already encoded in `config.py`) is enforced server-side before a value is written or a restart is suggested. |
| 7 | Change history | Yes — persisted (survives restarts), visible in the Settings UI. |
| 8 | Auth for saving a setting | Same JWT auth as everywhere else, PLUS an explicit confirmation step in the UI (a dialog) before the write — distinct from the lower-friction category-rename flow, given the behavioral/operational impact. |

## Functional Requirements

- **FR-CAS-1**: The Settings page SHALL expose exactly the 35 settings from the "Expose" + "Advanced" tables above as user-editable fields, and no others. All fields in the "Exclude" list (`db_user`, `db_password`, `db_host`, `db_port`, `db_name`, `jwt_secret`, `jwt_algorithm`, `gemini_api_key`, `openrouter_api_key`, `embedding_api_key`, `google_oauth_client_id`, `google_oauth_client_secret`, `google_drive_folder_id`, `google_drive_backup_folder_id`) SHALL NOT be exposed, readable, or writable through this feature's API surface, under any request shape.
- **FR-CAS-2**: The 7 "Advanced" settings SHALL be visually distinguished in the UI (e.g. a warning badge/section) from the 28 standard tunables, communicating that an incorrect value can silently degrade or break functionality (e.g. a wrong `embedding_base_url` soft-fails with no error; a wrong `embedding_dimensions` breaks the Qdrant collection; a wrong `frontend_origin` can lock the UI itself out via CORS).
- **FR-CAS-3**: The Settings page SHALL display each exposed setting's current effective value (the override value if one has been set, otherwise the deployment's configured/default value) and its owning service (Ingestion Worker vs. API Service).
- **FR-CAS-4**: Saving a setting SHALL write to a new, separate, non-secret override file (e.g. `config/runtime-overrides.env`), never to the root `.env` file.
- **FR-CAS-5**: Both `Settings` classes SHALL be updated to load the override file (via pydantic's `env_file` mechanism), with override values taking effect for any setting exposed by this feature. As part of this, `docker-compose.yml`'s existing gap (settings present in `config.py`/`.env.example` but missing from the `environment:` block — see Current Behavior) SHALL be closed for every setting exposed by this feature, and the interaction between docker-compose-supplied process env vars and the override file SHALL be resolved so the override actually takes effect (process env vars taking precedence over `env_file` in pydantic-settings' default order would otherwise silently make some overrides no-ops — see Assumptions).
- **FR-CAS-6**: After saving a setting, the UI SHALL indicate that a restart of the owning container is required, and display the exact command to run (e.g. `docker restart transactagent-worker`). No restart is triggered automatically.
- **FR-CAS-7**: For settings owned by `ingestion-worker`, the Settings page SHALL show the worker's current busy/idle state, derived from its existing heartbeat mechanism. The restart command SHALL only be presented as safe to run once the worker is idle; while busy, the UI SHALL indicate the worker is currently processing instead.
- **FR-CAS-8**: Each setting SHALL be validated server-side against its real type and range (matching its actual constraint in `config.py`, e.g. `embedding_similarity_threshold` ∈ [0.0, 1.0], `backup_schedule_hour` ∈ [0, 23], no negative thresholds/counts) before being written. Invalid values SHALL be rejected with a specific error and SHALL NOT be written to the override file.
- **FR-CAS-9**: Every successful settings change SHALL be recorded in a persisted history entry (setting name, previous value, new value, timestamp), and this history SHALL be viewable in the Settings UI.
- **FR-CAS-10**: Saving any setting SHALL require an explicit confirmation step in the UI (e.g. a confirmation dialog summarizing the change and which service needs restarting) in addition to the existing JWT auth already required for the underlying API call.

## Non-Functional Requirements

- **NFR-CAS-1 (Security)**: This feature SHALL NOT introduce Docker-socket access, `subprocess`-based process control, or any other host/container-orchestration privilege into any service. Restart remains entirely a human action outside the running application.
- **NFR-CAS-2 (Security)**: The "Exclude" list (FR-CAS-1) SHALL be enforced server-side (e.g. an explicit allow-list of writable setting keys), not only omitted from the UI — a request naming an excluded key SHALL be rejected, not silently accepted.
- **NFR-CAS-3 (Security)**: The override file SHALL be excluded from version control (git-ignored), consistent with the existing `.env` file's treatment, since it can contain deployment-specific endpoint values.
- **NFR-CAS-4 (Consistency)**: Per-field validation rules (FR-CAS-8) SHALL be derived from each field's actual `config.py` definition/constraint rather than duplicated ad hoc in a second place that could drift out of sync.
- **NFR-CAS-5 (Reliability)**: The busy/idle indicator (FR-CAS-7) SHALL reflect the worker's real, current state (heartbeat-derived), not a static or assumed value.
- **NFR-CAS-6 (Auditability)**: Change history (FR-CAS-9) SHALL be persisted in the database, not held only in memory, so it survives a container restart.

## Assumptions

- **Assumption 1**: "Extra confirmation step" (Resolved Decision 8) means a UI confirmation dialog before the write — not a second authentication factor or re-login — since the project has exactly one user account and no role/permission system to layer a stronger check on top of.
- **Assumption 2**: The exact technical fix for the process-env-vs-`env_file`-precedence interaction (FR-CAS-5) — e.g. whether `docker-compose.yml` stops explicitly mapping the now-overridable settings entirely, relying purely on file-based loading — is left to Functional/Application Design, not fully specified here; the direction (file-based override, plain restart, no recreate) is fixed by Resolved Decision 3.
- **Assumption 3**: Closing the `docker-compose.yml` env-passthrough gap (FR-CAS-5) is scoped only to the 35 settings this feature exposes, not a project-wide cleanup of every other unmapped variable.
- **Assumption 4**: `google_drive_folder_id`/`google_drive_backup_folder_id` remain excluded, as originally proposed — neither Resolved Decision 1 nor any answer text moved them into scope.

## Out of Scope

- Any automated or Docker-socket-triggered container restart (Resolved Decision 2) — a genuinely different feature if wanted later.
- Hot-reload of any setting without a restart — no setting becomes live without the owning container restarting.
- Exposing any credential/secret (`db_user`, `db_password`, `db_host`, `db_port`, `db_name`, `jwt_secret`, `jwt_algorithm`, `gemini_api_key`, `openrouter_api_key`, `embedding_api_key`, `google_oauth_client_id`, `google_oauth_client_secret`) or the two Google Drive folder IDs.
- A multi-user roles/permissions system — this feature reuses the existing single-user JWT auth model as-is (Assumption 1).
- A busy/idle indicator or restart-timing guidance for `api-service` itself — `api-service` handles synchronous request/response with no equivalent in-flight-file concern to `ingestion-worker`'s poll loop, so FR-CAS-7 applies only to Ingestion Worker settings.

## Post-Approval Change (2026-08-16, discovered during API Service Code Generation): Setting Count Corrected from 35 to 40

While building the actual allow-list catalog (API Service's `app_settings/catalog.py`, AR-28) directly against every distinct field name in both services' real `config.py` files, the true count came out to 40, not 35. The undercount traced to four rows in the original classification tables (`configurable-app-settings-questions.md`, carried forward into Resolved Decision 1/FR-CAS-1 above) that each named **two** settings separated by "/" but were counted as one row: `recurring_payment_detection_cadence_min_days / _max_days`, `default_page_size / max_page_size`, `embedding_model / embedding_dimensions`, and `qdrant_host / qdrant_port` — 4 rows undercounted by 1 each, 28+7 rows -> 30+10 actual settings = 40.

No scope actually changed — every setting named in those combined rows was always intended to be included (Q1 = C chose "the full Expose table AND the Advanced table," not a partial list); this is purely a summary-count correction, not a new decision. `FR-CAS-1`, Resolved Decision 1, and Assumption 3 above all still say "35" and are superseded by this section for the count specifically — their substance (which settings, how enforced) is unchanged. The Database and API Service Functional Design artifacts (`business-rules.md` AR-28's table, `SettingChange`'s domain-entities.md note) already listed all 40 individually and needed no correction; only summary-count mentions elsewhere were wrong.
