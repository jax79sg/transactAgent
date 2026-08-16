# User Stories — Configurable Application Settings

Appends **Epic 10** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7, `recurring-payments-stories.md` Epic 8, `embedding-similarity-stories.md` Epic 9), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then + edge cases — matches the existing convention.
**Traceability**: Each story references `configurable-app-settings-requirements.md`'s FR-CAS/NFR-CAS IDs.
**Naming note**: the new Settings-page section is titled "Application Settings" with an "Advanced" sub-heading, per the stated assumption in the story plan.

---

## Epic 10: Configurable Application Settings

### US-10.1: Edit a standard setting without touching `.env` or restarting anything myself first
**As** the Account Owner, **I want** to view and edit an application setting's current value directly in the Settings page, with my change validated and confirmed before it's saved **so that** I can tune things like matching thresholds or the poll interval without SSHing in or hand-editing `.env`.

**Traces to**: FR-CAS-1, FR-CAS-3, FR-CAS-4, FR-CAS-6, FR-CAS-8, FR-CAS-10, NFR-CAS-1, NFR-CAS-2, NFR-CAS-3, NFR-CAS-4

**Acceptance Criteria**:
- *Happy path*: Given I open the "Application Settings" section, When I view a setting, Then I see its current effective value and which service owns it (Ingestion Worker or API Service).
- *Happy path — edit and save*: Given I change a setting to a valid new value, When I confirm the change in the confirmation dialog, Then the value is written to the non-secret override file (never the root `.env`), and I'm shown that the owning service needs restarting along with the exact command to run.
- *Edge case — invalid value rejected*: Given I enter a value outside the setting's real type/range (e.g. a negative threshold, an out-of-range hour), When I try to save, Then it's rejected with a specific error and nothing is written — no restart is suggested for a change that never took effect.
- *Edge case — secrets never reachable*: Given any request to this feature's settings API, When it names a credential/secret field (e.g. `db_password`, `jwt_secret`, any `*_api_key`, either Google Drive folder ID), Then it is rejected — these fields are never readable or writable through this surface, regardless of how the request is shaped.
- *Edge case — no silent auto-apply*: Given I've entered a valid new value, When I have not yet confirmed it in the dialog, Then nothing is written — the confirmation step is required every time, same as every other save in this feature.

### US-10.2: Know which settings are riskier before I touch them
**As** the Account Owner, **I want** the settings that are safe to expose but easy to break something with (like the embedding endpoint URL or the CORS origin list) clearly marked as "Advanced" **so that** I don't casually change something that silently breaks a feature or locks me out of the app.

**Traces to**: FR-CAS-2

**Acceptance Criteria**:
- *Happy path*: Given I open the "Application Settings" section, When I look at the list, Then the 7 Advanced settings (`embedding_base_url`, `embedding_model`, `embedding_dimensions`, `openrouter_base_url`, `openrouter_model`, `gemini_model`, `frontend_origin`, `google_oauth_redirect_uri`, `qdrant_host`, `qdrant_port`) are visually separated under an "Advanced" sub-heading, distinct from the standard tunables.
- *Edge case — warning is specific, not generic*: Given I start editing an Advanced setting, When the warning is shown, Then it names the actual consequence of getting it wrong for that setting (e.g. "a wrong value here disables embedding matching with no error shown" for `embedding_base_url`), not a generic "be careful" message.

### US-10.3: See whether it's actually safe to restart the Ingestion Worker right now
**As** the Account Owner, **I want** to see whether the Ingestion Worker is currently mid-cycle before I run the restart command it gave me **so that** I don't interrupt an in-flight statement import by restarting at the wrong moment.

**Traces to**: FR-CAS-7, NFR-CAS-5

**Acceptance Criteria**:
- *Happy path — idle*: Given I've just saved a change to an Ingestion-Worker-owned setting and the worker is currently idle (per its heartbeat), When I view the restart guidance, Then it's shown as safe to run now, with the exact command.
- *Happy path — busy*: Given the worker is mid-poll-cycle (e.g. actively processing a statement) when I save the change, When I view the restart guidance, Then it tells me the worker is currently processing instead of presenting the restart command as ready, and updates to "safe to restart" once the worker goes idle.
- *Edge case — API-Service-only settings unaffected*: Given the setting I changed is owned by `api-service` (not Ingestion Worker), When I view the restart guidance, Then no busy/idle indicator is shown — just the restart-required message and command, since `api-service` has no equivalent in-flight-file concern.

### US-10.4: Look back at what settings changed and when
**As** the Account Owner, **I want** to see a history of setting changes (old value, new value, when) **so that** if matching or categorization behavior suddenly seems different, I can check whether a setting change explains it.

**Traces to**: FR-CAS-9, NFR-CAS-6

**Acceptance Criteria**:
- *Happy path*: Given I've changed one or more settings over time, When I view the change history in the Settings UI, Then I see each change's setting name, previous value, new value, and timestamp, most recent first.
- *Edge case — survives a restart*: Given I restart the app stack (any or all containers), When I view the change history afterward, Then every prior entry is still there — it's stored in the database, not held only in a running process's memory.
