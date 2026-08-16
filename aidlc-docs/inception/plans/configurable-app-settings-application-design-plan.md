# Application Design Plan — Configurable Application Settings

**Role**: Software architect, converting `configurable-app-settings-requirements.md` and `configurable-app-settings-stories.md` (Epic 10) into component-level design.

## Genuinely open item

None requiring a new user question — the two rounds of Requirements Analysis questions already resolved every product-level decision (scope, restart model, persistence mechanism, busy/idle gating, placement, validation, history, auth). What follows are architecture/design decisions at the appropriate altitude for this stage (component boundaries, method signatures, dependencies) — not detailed business rules, which stay deferred to Functional Design. Each is documented, not asked, consistent with this project's established practice, and flagged here for correction at the review gate if any reads wrong.

## Key Design Resolution 1: extend the existing Configuration Component — no new component

`components.md` already has a **Configuration Component** (API Service) whose stated purpose is "Manage user-editable configuration that isn't a secret" — currently scoped to the category whitelist (US-5.2), with an explicit note that secrets stay environment-variable-only. This feature's entire premise (non-secret, user-editable configuration) is exactly this component's existing charter, just extended from "categories" to "the 35 in-scope application settings." Extending it, rather than inventing a new "Settings Component," keeps the project's established pattern of extending an existing component when the new capability is a natural continuation of its stated purpose (mirrors how Categorization Engine absorbed the always-on-LLM change rather than spawning a new component).

**Resolution**: Configuration Component gains: `listSettings`, `getSetting`, `updateSetting`, `listSettingHistory`, `getRestartGuidance`. The existing category-whitelist methods are unchanged. The component's "secrets stay env-var-only" note is narrowed, not removed: it now applies only to the 13 excluded credential/secret fields — the 35 in-scope settings move from "env-var-only" to "editable here, env-var as the underlying mechanism."

## Key Design Resolution 2: the busy/idle signal reuses existing DB state — no new table, no new shared-status file

FR-CAS-7 needs to know whether `ingestion-worker` is "mid-cycle" before showing the restart command as safe. The obvious-looking approach — a new shared status file or DB table the worker updates every poll cycle — was considered and rejected: `poll_once()` already claims a queued `IngestionRun` (or `RecategorizationJob`) by setting its `status` to `running` before processing it, and clears it back to a terminal status when done (`main.py`/`repository.py`, existing code). That is already a complete, precise, currently-true signal for "am I actively mid-statement-import right now" — the exact case Clarification 1 was worried about (Q4/Q2 tension: restarting while a statement is being processed).

**Resolution**: "Busy" = at least one `IngestionRun` or `RecategorizationJob` row currently has `status = 'running'`. Configuration Component's `getRestartGuidance()` answers the busy/idle question with a **Shared DB query against tables that already exist** — no new table, no new shared file, no new write path on the Worker side. This keeps the "API Service and Ingestion Worker Service coordinate only through the Shared DB, never a direct call" architectural rule **fully intact** for this piece — deliberately not extended to cover it, since it doesn't need to be. (The lower-priority poll_once() branches — backup, detection scan, embedding batch — are excluded from "busy" on purpose: all three are already documented elsewhere in this project as safe-to-interrupt/resume, unlike an in-flight statement import.)

## Key Design Resolution 3: the settings override needs a new, genuinely new kind of cross-service channel — a shared file volume, not the DB

Resolved Decision 3 (Requirements) fixed the mechanism: a file, loaded via pydantic's `env_file` support, not a DB-stored value. This isn't a stylistic choice available to revisit here — it's forced by a real ordering constraint: `Settings()` (in both services) is constructed once at module import, and its own fields *include* the DB connection parameters (`db_host`, `db_port`, `db_user`, `db_password`). A DB-backed override mechanism would need a DB connection to read the overrides needed to... determine how to connect to the DB. A file has no such chicken-and-egg problem — it's readable before any connection exists.

**Resolution**: a new shared Docker volume, bind-mounted into both `api-service` and `ingestion-worker` containers, holding one file — the non-secret override-settings file (exact path/format is Infrastructure Design's job, per the execution plan). API Service (Configuration Component) writes it on `updateSetting()`; both services' `Settings` classes read it via `env_file` at process start. This is a genuinely new kind of cross-service coordination — not a "direct call" (no RPC, no synchronous request/response, no availability coupling — one side writes, the other passively reads on its own next startup) — so it preserves the *spirit* of "API Service and Ingestion Worker Service never call each other directly" even though it's mechanically new (a second kind of shared state, alongside the Shared DB, justified by the one constraint that actually requires it).

## Key Design Resolution 4: change history is a new, narrow entity — not bolted onto an existing one

None of the existing history-shaped tables fit: `recategorization_proposals`/`categorization_disagreements` are about category decisions, not settings; there's no existing generic "audit log" entity anywhere in the schema. A new, narrow entity is more consistent with this project's established precedent (`backup_runs`, the recurring-payments tables, and `categorization_disagreements` were all purpose-built rather than folded into something adjacent-but-not-quite-right).

**Resolution**: a new Database entity, **`SettingChange`** — one row per successful `updateSetting()` call (at the Application Design altitude; exact columns are Database Functional Design's job: setting name, previous value, new value, timestamp — per FR-CAS-9). Written and read only by the Configuration Component (API Service). The Ingestion Worker Service has no involvement with this table — it doesn't need its own change history; it only ever reads its *current effective* configuration (via `env_file`), never a history of how it got there.

## Component Boundary Note: allow-list enforcement is data, not a new component

NFR-CAS-2 requires the exclusion list to be enforced server-side, not just hidden in the UI. This is implemented as a static allow-list (the 35 setting names, each with its owning service + type/range metadata) that `updateSetting`/`getSetting`/`listSettings` all consult — a data structure Configuration Component owns, not a separate "validation component." Any setting name not on the allow-list (including every excluded secret) is rejected before any file write or DB read is attempted, by construction — there's no code path that can reach a secret's actual value at all, since the allow-list, not a denylist, is what's consulted.

## Frontend

The existing Frontend SPA component convention (one component covers every page, per the established addendum pattern) is reused as-is — a new "Application Settings" section (with an "Advanced" sub-heading) added to the existing `SettingsPage.tsx`, consuming Configuration Component's new endpoints. No new Frontend component.

## Mandatory Design Artifacts

- [x] Update `components.md` — Configuration Component addendum (Key Design Resolution 1), Frontend SPA addendum, Shared Data Store addendum (`setting_changes` table)
- [x] Update `component-methods.md` — Configuration Component's 5 new method signatures
- [x] Update `services.md` — new orchestration flow for `updateSetting` (validate → write override file → record history → compute restart guidance); new "Cross-Service Coordination: Settings Override File" section alongside the existing Run/Job Queue one
- [x] Update `component-dependency.md` — Configuration Component's new dependencies (Shared DB `setting_changes` table; read-only query of `ingestion_runs`/`recategorization_jobs` for busy/idle; the new shared volume, write side); Ingestion Worker Service's new dependency (the same shared volume, read side, via `env_file`); updated data flow diagram
- [x] Update `application-design.md` — consolidated summary
