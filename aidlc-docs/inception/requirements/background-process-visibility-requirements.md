# Background Process Visibility — Requirements

## Intent Analysis Summary

- **User request**: "I would like a new feature where its easy to tell if there's background processes that's running. One Examlpe is when i change category, there's this review of trasnactions and offering suggestions."
- **Request type**: New Feature (UI/UX — background activity visibility)
- **Scope estimate**: Multiple Components (Frontend + API Service; Database/Ingestion Worker unchanged for this phase — see FR-BPV-1)
- **Complexity estimate**: Moderate

## Background (from live-system research)

- The Ingestion Worker's `poll_once()` processes exactly one background job per 5-second cycle, checked in priority order: ingestion run → recategorization job → backup run → detection scan → embedding batch.
- Only **ingestion runs** and **recategorization jobs** (the user's own example) have a real `queued`/`running` status in the database today, each with `started_at`/`created_at` and `completed_at` timestamps. The other three job types are write-once-at-completion by design — showing them "in progress" would need a schema change, not just UI, and is out of scope for this phase (FR-BPV-1 / User Answer Q1).
- A directly reusable precedent exists: `app_settings/repository.py`'s `is_ingestion_worker_busy()` — an `EXISTS`-OR query over `IngestionRun.status='running'` OR `RecategorizationJob.status='running'` — already exposed via `GET /app-settings/{name}/restart-guidance` and consumed by `SettingsPage.tsx`. This feature needs its own endpoint (broader payload: which job type, plus recent history) rather than reusing that one directly, since restart-guidance's response shape is narrowly scoped to that use case.
- `NavBar.tsx` has two existing badge components (`PendingReviewBadge`, `RecurringPaymentsBadge`), both backlog counts on a 30s/5min poll, both using the same amber-pill visual style. Neither represents "something is happening right now."

## Functional Requirements

- **FR-BPV-1 (Scope)**: This feature covers exactly the two job types with real in-progress tracking today — ingestion runs and recategorization jobs. Backup runs, recurring-payment detection scans, and embedding batches are explicitly out of scope for this phase; extending to them requires a future schema change (adding a genuine in-progress status) and is tracked as a follow-up, not built now.
- **FR-BPV-2 (Nav bar indicator)**: A persistent indicator in the nav bar, visible on every page, shows when a background job (ingestion run or recategorization job) is currently running.
- **FR-BPV-3 (Detail panel)**: Clicking/opening the nav bar indicator (or a dedicated panel reachable from it) shows more detail: which job type is currently running, plus a short list of recently-completed background activity (e.g. "Ingestion run completed 2 minutes ago", "Recategorization scan completed at 09:14").
- **FR-BPV-4 (Idle state)**: When nothing is running and there is no recent history to show, the indicator is unobtrusive/hidden, consistent with the existing badge components' "hide when nothing to report" pattern.
- **FR-BPV-5 (Job identification)**: When a job is running, the indicator/panel identifies which one — "Ingestion run in progress" vs. "Recategorization scan in progress" — never a generic "something is running" with no detail, since the worker only ever runs one job at a time and that information is cheaply available.
- **FR-BPV-6 (Recent history source)**: The "recently completed" list is built from `IngestionRun` and `RecategorizationJob` rows ordered by `completed_at`, filtered to a recent window (exact window and item count to be set in Functional/NFR Design) — no new database tables or columns required for the two in-scope job types.
- **FR-BPV-7 (New API endpoint)**: A new API Service endpoint (exact route/shape decided in Functional Design) reports: whether a job is currently running and which type, plus the recent-history list described in FR-BPV-6. This is separate from the existing `restart-guidance` endpoint, which stays scoped to its own use case.

## Non-Functional Requirements

- **NFR-BPV-1 (Refresh cadence)**: The nav bar indicator polls fast enough to feel close to real-time — a few seconds — matching the existing Ingestion page's own active-run polling behavior, not the slower 30s/5min cadence used by the two backlog-count badges.
- **NFR-BPV-2 (Visual distinction)**: The running-indicator's visual style is deliberately distinct from the existing amber-pill count badges (e.g. a spinner or pulsing indicator) — "a job is running right now" and "N items are waiting for you" are different kinds of information and should not look the same at a glance.
- **NFR-BPV-3 (No added polling load when idle)**: Polling continues at the fast cadence regardless of running/idle state (simplicity, matches existing precedent), but the payload stays minimal (a status flag, a job-type enum, and a short history array) to keep the cost of frequent polling low.
- **NFR-BPV-4 (Consistency)**: Reuses the existing `useQuery`/`refetchInterval` polling pattern already used by `PendingReviewBadge`/`RecurringPaymentsBadge`, rather than introducing a new data-fetching mechanism.
- **NFR-BPV-5 (No new schema)**: This phase introduces no database migrations — it reads existing `IngestionRun`/`RecategorizationJob` columns only.

## User Answers (from `background-process-visibility-questions.md`)

| # | Question | Answer |
|---|---|---|
| 1 | Which job types to cover | C — the two with real tracking now (ingestion runs, recategorization jobs); backup/scan/embedding as a later follow-up |
| 2 | Placement | C — both a persistent nav bar indicator and more detail on click/dedicated panel |
| 3 | Content | C — which job is running, plus a short history of recently-completed activity |
| 4 | Refresh cadence | A — fast, a few seconds, close to real-time |
| 5 | Visual style | B — visually distinct from the existing count-badges (spinner/pulsing), not another amber pill |

**Note on Q1/Q3 interaction**: Q3's "history" option was originally framed as most useful for the three write-once job types excluded by Q1. Resolved without a follow-up question: both in-scope job types (`IngestionRun`, `RecategorizationJob`) already have real `completed_at` timestamps, so a recent-completions history is fully achievable for them within this phase's scope (FR-BPV-6) — no contradiction, just a scope note.

## Summary

This feature adds a fast-polling (few-second), visually distinct (non-badge) nav bar indicator plus a detail panel showing which of the two trackable background job types (ingestion run, recategorization job) is currently running, along with a short recent-completions history for both. Backup runs, detection scans, and embedding batches are explicitly deferred — they would require a database schema change to track "in progress" state, which is out of scope here. No new database migrations are needed for this phase.
