# User Stories — Background Process Visibility

Appends **Epic 11** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7, `recurring-payments-stories.md` Epic 8, `embedding-similarity-stories.md` Epic 9, `configurable-app-settings-stories.md` Epic 10), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then + edge cases — matches the existing convention.
**Traceability**: Each story references `background-process-visibility-requirements.md`'s FR-BPV/NFR-BPV IDs.

---

## Epic 11: Background Process Visibility

### US-11.1: See at a glance that something is running, from anywhere in the app
**As** the Account Owner, **I want** a persistent nav bar indicator that lights up whenever an ingestion run or recategorization job is actively processing **so that** I don't have to guess whether the app is busy or wonder why a page feels slow.

**Traces to**: FR-BPV-2, FR-BPV-4, FR-BPV-5, NFR-BPV-1, NFR-BPV-2, NFR-BPV-4

**Acceptance Criteria**:
- *Happy path — job running*: Given an ingestion run or recategorization job is currently `running`, When I'm on any page of the app, Then the nav bar shows an active indicator (visually distinct from the existing amber-pill count badges — e.g. a spinner or pulsing dot, not a number).
- *Happy path — idle*: Given no background job is currently running, When I'm on any page, Then the indicator is hidden/unobtrusive, consistent with how the existing `PendingReviewBadge`/`RecurringPaymentsBadge` hide when there's nothing to report.
- *Freshness*: Given a job transitions from running to completed (or a new one starts) while I'm looking at the nav bar, When the next poll cycle fires, Then the indicator updates within a few seconds — close to real-time, not the slower 30s/5min cadence used by the existing count badges.

### US-11.2: Know exactly what's running, not just that something is
**As** the Account Owner, **I want** the indicator to tell me specifically whether it's an ingestion run or a recategorization job that's active **so that** I understand what the app is doing right now instead of an unhelpful generic "busy" signal.

**Traces to**: FR-BPV-5, FR-BPV-7

**Acceptance Criteria**:
- *Happy path — ingestion running*: Given an ingestion run is `running`, When I open the indicator/panel, Then it reads something like "Ingestion run in progress" — not a generic "something is running."
- *Happy path — recategorization running*: Given a recategorization job is `running`, When I open the indicator/panel, Then it reads something like "Recategorization scan in progress."
- *Edge case — only one at a time*: Given the worker only ever processes one job at a time, When I open the panel, Then at most one "currently running" entry is ever shown, never two simultaneously.

### US-11.3: Check what background activity happened recently, in one place
**As** the Account Owner, **I want** to click into a detail panel and see a short list of recently-completed ingestion runs and recategorization jobs, with when they finished **so that** I can confirm something actually ran (e.g. after I triggered a recategorization) without hunting through the Ingestion or Review pages separately.

**Traces to**: FR-BPV-3, FR-BPV-6, FR-BPV-7

**Acceptance Criteria**:
- *Happy path*: Given one or more ingestion runs or recategorization jobs have completed recently, When I open the detail panel, Then I see them listed with job type and a relative-or-absolute completion time, most recent first.
- *Edge case — nothing recent*: Given no job of either type has run recently, When I open the detail panel, Then it clearly shows there's no recent activity rather than an empty/broken-looking list.
- *No schema change*: Given this history is read from existing `IngestionRun`/`RecategorizationJob` rows only (per FR-BPV-6), When the feature ships, Then no new database table or migration is required to support it.

---

## Traceability Summary

| Story | Requirements Covered |
|---|---|
| US-11.1 | FR-BPV-2, FR-BPV-4, FR-BPV-5, NFR-BPV-1, NFR-BPV-2, NFR-BPV-4 |
| US-11.2 | FR-BPV-5, FR-BPV-7 |
| US-11.3 | FR-BPV-3, FR-BPV-6, FR-BPV-7 |

FR-BPV-1 (scope decision) and NFR-BPV-3/NFR-BPV-5 (payload minimalism, no new schema) are cross-cutting constraints reflected across all three stories rather than a dedicated story of their own.
