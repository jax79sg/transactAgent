# Code Generation Plan — Ingestion Worker Service Unit — Nightly Transaction Backup

**Unit**: Ingestion Worker Service (Unit 3). **Stories**: US-7.1–US-7.4.
**Dependencies**: Database unit (`BackupRun` table, migration 0006) — complete.
**New module**: `ingestion_worker/backup/` (`repository.py`, `service.py`), matching the existing per-concern package convention (`categorization/`, `currency/`, `duplicate_detection/`).

## Steps

1. [x] **Config**: add `google_drive_backup_folder_id` (default: the dedicated folder ID from Requirements Clarification 2), `backup_schedule_hour` (default 2, FR-2), `backup_retention_count` (default 7, FR-7) to `config.py`
2. [x] **Drive Connector extension**: add `ensure_backup_folder_exists`, `upload_file`, `list_backup_folder_files`, `delete_file` to `clients/drive_client.py`, reusing `_load_credentials`/`retry_with_backoff`/`_TRANSIENT_HTTP_STATUS` exactly as the existing methods do; extend `DriveFileRef` with an optional `created_time` field (backward compatible — existing callers unaffected)
3. [x] **Business Logic Generation**: create `backup/service.py` — `is_backup_due_now`, `run_backup`, `_build_csv`, `_enforce_retention`, implementing WR-11..15
4. [x] **Repository Layer Generation**: create `backup/repository.py` — `find_backup_run_for_date`, `record_backup_run`
5. [x] **Orchestration wiring**: extend `main.py`'s `poll_once()` with the third branch (`services.md` addendum) — checked only when no run/job was found this cycle
6. [x] **Unit Testing**:
   - `tests/test_drive_client.py` — added 4 test classes for the new methods (folder-exists/create, upload, paginated list, delete)
   - `tests/test_backup_service.py` (new) — `is_backup_due_now` (before/after schedule hour, already-ran-today), `run_backup` (success path, Drive-connectivity failure paths ×3, generic-exception failure path, WR-12's "never raises"/"exactly one row" guarantees), `_enforce_retention` (keeps configured most-recent count, no-op under the limit, ignores non-matching filenames)
   - `tests/test_main_loop.py` — extended `TestPollOnce` with 3 new tests covering the third-branch dispatch priority
7. [x] **Documentation Generation**: created `aidlc-docs/construction/ingestion-worker/code/backup-summary.md`

## Verification (not deferred to Build & Test — done now, live)

- [x] Ran the full `ingestion-worker` unit test suite: 133/133 passing, zero regressions
