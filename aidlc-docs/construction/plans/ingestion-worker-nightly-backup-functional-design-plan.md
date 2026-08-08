# Functional Design Plan — Ingestion Worker Service Unit — Nightly Transaction Backup

**Unit**: Ingestion Worker Service (Unit 3). **Scope**: new **Backup Manager Component** (`isBackupDueNow`, `runBackup`, `enforceRetention`), and an extension of the existing **Drive Connector Component** (`ensureBackupFolderExists`, `uploadFile`, `listBackupFolderFiles`, `deleteFile`), per Application Design.

## No blocking questions, but one design point worth surfacing explicitly

Every business rule needed follows directly from Requirements (FR-1..11) and Application Design's method signatures. One implementation consequence is worth calling out because it isn't obvious from the requirements text alone:

**Catch-up (FR-8/US-7.3) requires no special-case code.** `isBackupDueNow()` is checked on every poll cycle unconditionally (per `services.md`'s `poll_once()` addendum), not just "at startup." Its logic is simply: *is it past today's scheduled time, and does no `BackupRun` row exist yet for today's `backup_date`?* If the worker was down at 02:00 and comes back at 09:00, the very next poll cycle already satisfies both conditions — it runs immediately, with no separate "was I just restarted" flag or startup hook needed. This is simpler than `main.py`'s existing `recover_stale_state()` (which exists because `IngestionRun`/`RecategorizationJob` have a `running` interim state that can be orphaned) — `BackupRun`'s write-once design (Database Functional Design) means there's nothing to orphan in the first place.

A second point, also a direct consequence of BR-17 rather than a new decision: **`runBackup()` must catch every exception internally and always write exactly one `BackupRun` row before returning.** If an unexpected error escaped uncaught, no row would be written for that attempt, and `isBackupDueNow()` would keep returning `true` every 5-second poll cycle for the rest of the day — a silent retry storm that directly violates FR-9's no-same-night-retry intent. This makes BR-17's uniqueness constraint the actual enforcement mechanism for FR-9, not just a data-integrity nicety.

## Execution Checklist

- [ ] Add WR-11..WR-15 to `business-rules.md`:
  - WR-11: Backup due determination (schedule + catch-up, per the reasoning above)
  - WR-12: Every attempt records exactly one outcome, no exception may escape `runBackup()` (the FR-9 enforcement mechanism)
  - WR-13: CSV snapshot content — full `transactions` table snapshot, all columns as stored (FR-6), one export per attempt
  - WR-14: Backup folder resolution and retention scope — separate dedicated Drive folder + `backup` subfolder (FR-3/FR-4), retention only ever considers files matching this feature's own naming convention (NFR-4)
  - WR-15: Failure classification — `drive_connectivity` vs `other` (FR-10/FR-11), used by the API Service's Backup Status Component
- [ ] Add a **Backup Manager Component** section to `business-logic-model.md` describing the `runBackup()` flow as pseudocode, matching the style of the existing Ingestion Orchestrator/Categorization Engine sections
- [ ] Add an addendum to the **Drive Connector Component** section of `business-logic-model.md` describing the 4 new methods
- [ ] Add an addendum to `domain-entities.md` — no new internal DTO needed beyond what's already in Unit 1's `BackupRun` schema; note the CSV row shape is just a direct column-for-column dump of `Transaction`, not a separate transformed shape
- [ ] New config setting needed (flagged for Code Generation, not a Functional Design question): `google_drive_backup_folder_id`, distinct from the existing `google_drive_folder_id`, per FR-3/FR-4 and the requirements clarification that moved backups to a separate dedicated folder
