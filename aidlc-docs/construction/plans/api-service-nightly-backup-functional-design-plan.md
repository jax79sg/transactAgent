# Functional Design Plan — API Service Unit — Nightly Transaction Backup

**Unit**: API Service (Unit 2). **Scope**: new **Backup Status Component** — a single read-only endpoint exposing the latest `BackupRun` row to the Frontend's Review page panel.

## No blocking questions, one gap worth resolving explicitly

Application Design's `getLatestBackupStatus() -> BackupStatus` signature and the Database unit's `BackupRun` schema together specify almost everything needed. One gap: neither specifies what to return **before any backup has ever run** (e.g. right after this feature is first deployed, before the first scheduled 02:00 attempt). This isn't a product question — it's a direct consequence of `BackupRun` being write-once with no row created in advance (Database Functional Design): there is no `BackupRun` row to read yet, so `getLatestBackupStatus()` must have a defined "nothing yet" response rather than erroring or fabricating a value.

**Resolution**: `outcome` is nullable in the response DTO. `null` means "no backup has run yet" — a third state the Frontend panel already needs to handle gracefully regardless (a blank panel or "no backups yet" message, not an error), distinct from both `success` and `failed`.

## Execution Checklist

- [ ] Add AR-14 to `business-rules.md`: no-prior-backup response shape (the resolution above)
- [ ] Add `BackupStatusResponse` DTO to `domain-entities.md` (Backup section, matching the `ProposalDTO` documentation style)
- [ ] Add a **Backup Status** section to `business-logic-model.md` describing the single read (query most recent `BackupRun` by `backup_date`, map to DTO, `null` outcome when no row exists)
- [ ] New router: `/backups` (GET only), matching the existing router-per-module convention (`recategorization`, `ingestion`, etc.) — registered in `main.py`
