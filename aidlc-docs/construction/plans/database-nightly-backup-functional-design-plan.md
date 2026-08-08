# Functional Design Plan — Database Unit — Nightly Transaction Backup

**Unit**: Database (Unit 1). **Scope**: one new entity, `BackupRun`, tracking each nightly backup attempt.

## No blocking questions

The shape of this entity follows directly from decisions already made in Requirements Analysis (FR-8, FR-9, FR-10) and Application Design (Backup Manager's `runBackup()`/`isBackupDueNow()`, Backup Status's `getLatestBackupStatus()`) — there is no genuine open business-logic question left for the Database unit specifically.

One design point worth stating explicitly (a technical call, not a product question): unlike `IngestionRun`/`RecategorizationJob`, `BackupRun` needs no `queued`/`running` interim status. Those two entities exist to coordinate *across* services (API Service enqueues, Ingestion Worker Service claims and updates) — a genuine cross-process handoff. A backup attempt is entirely synchronous within a single Ingestion Worker poll cycle (Application Design: `services.md`'s `poll_once()` addendum) — nothing else claims or updates it mid-flight. So `BackupRun` is write-once: a single row is inserted only when the attempt finishes, already in its terminal state (`success` or `failed`). This also directly satisfies the FR-8/FR-9 "has today's backup already been attempted" check and the "no same-night retry" rule with one simple uniqueness constraint, rather than needing status-transition logic.

## Execution Checklist

- [ ] Add `BackupRun` entity to `domain-entities.md`, addendum-dated, matching the existing entity documentation format:
  - `id`, `backup_date` (unique), `started_at`, `completed_at`, `outcome` (`success`|`failed`), `failure_category` (`drive_connectivity`|`other`, nullable), `transaction_count` (nullable), `backup_filename` (nullable)
- [ ] Add business rules to `business-rules.md` (starting at BR-17):
  - One `BackupRun` row per calendar `backup_date` (backs both "only once per day" US-7.1 and "no same-night retry" FR-9/US-7.4 with a single constraint)
  - `failure_category` is null iff `outcome = 'success'`
- [ ] Add to `business-logic-model.md`: `BackupRun` as a write-once/terminal-only record (no state machine, unlike `IngestionRun`/`RecategorizationJob`) — explain why, per the reasoning above
- [ ] No ER diagram edge needed to other entities — `BackupRun` is standalone (doesn't reference `Transaction` rows individually; it's a per-attempt summary, not a per-item audit trail)
