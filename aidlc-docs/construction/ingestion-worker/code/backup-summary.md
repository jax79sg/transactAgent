# Backup Manager — Code Summary (Epic 7, Nightly Transaction Backup)

New package: [`ingestion_worker/backup/`](../../../../ingestion-worker/src/ingestion_worker/backup/).

| File | Purpose |
|---|---|
| `repository.py` | `find_backup_run_for_date` (WR-11's due-check), `record_backup_run` (WR-12's single write path) |
| `service.py` | `is_backup_due_now`, `run_backup`, `_build_csv`, `_enforce_retention` — implements WR-11..15 |

## Key implementation decisions

- **Catch-up needs no special code** (per the functional design plan): `is_backup_due_now()` is a pure function of "past the schedule hour" + "no `BackupRun` row yet today," checked unconditionally on every poll cycle. A worker that was offline at 02:00 and returns at 09:00 satisfies both conditions on its very next cycle.
- **`run_backup()` never raises**: every exception path (Drive connectivity errors, any other exception) is caught internally and always results in exactly one `record_backup_run()` call before returning — this is what makes `BackupRun`'s `backup_date` uniqueness (BR-17) actually enforce FR-9's no-same-night-retry rule at the application level, not just the schema level.
- **Failure classification**: `DriveNotConnectedError`, `DriveReauthRequiredError`, `TransientError`, and `HttpError` (all from/via `clients/drive_client.py`) are classified `drive_connectivity`; anything else is `other`.
- **Retention scope**: `_enforce_retention` only ever considers files whose name matches `transactions-backup-*.csv` — a non-matching file already in the folder is never a deletion candidate, regardless of age.

## `clients/drive_client.py` additions

4 new functions (`ensure_backup_folder_exists`, `upload_file`, `list_backup_folder_files`, `delete_file`), all reusing the existing `_load_credentials`/`retry_with_backoff`/`_TRANSIENT_HTTP_STATUS` machinery — same OAuth credential and transient-error handling as the pre-existing `list_folder_pdf_files`/`download_file`, scoped to the separate, dedicated backup Drive folder. `DriveFileRef` gained an optional `created_time` field (backward compatible).

## `config.py` additions

`google_drive_backup_folder_id` (defaults to the dedicated folder ID from Requirements Clarification 2), `backup_schedule_hour` (default 2), `backup_retention_count` (default 7).

## `main.py` wiring

`poll_once()` gained a third branch, checked only when no run or job was found that cycle — see `services.md`'s Application Design addendum for the full reasoning.

## Tests

- `tests/test_drive_client.py`: 4 new test classes for the Drive Connector additions
- `tests/test_backup_service.py` (new): `is_backup_due_now`, `run_backup` (success + 4 failure-classification scenarios + the "never raises" guarantee), `_enforce_retention` (limit enforcement, no-op under the limit, naming-convention scoping)
- `tests/test_main_loop.py`: extended `TestPollOnce` with 3 new tests covering the third branch's dispatch priority

Full suite: 133/133 passing.
