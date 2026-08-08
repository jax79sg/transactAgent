# Code Generation Plan — API Service Unit — Nightly Transaction Backup

**Unit**: API Service (Unit 2). **Stories**: US-7.4 (status exposure only).
**Dependencies**: Database unit (`BackupRun` table) — complete.
**New module**: `api_service/backup/` (`repository.py`, `service.py`, `router.py`, `schemas.py`), matching the existing per-module convention (`recategorization/`, `ingestion/`, etc.).

## Steps

1. [x] **Repository Layer Generation**: `backup/repository.py` — `get_latest_backup_run`
2. [x] **Business Logic Generation**: `backup/service.py` — `get_latest_backup_status` (AR-14's no-prior-backup null handling)
3. [x] **Schemas**: `backup/schemas.py` — `BackupStatusResponse` (CamelModel)
4. [x] **API Layer Generation**: `backup/router.py` — `GET /backups/status`, auth-protected like every other router
5. [x] **Router registration**: `main.py` — imported and `include_router`
6. [x] **Unit Testing**:
   - `tests/test_backup_service.py` (new) — latest-row selection, no-prior-backup null response, failed-with-category response, most-recent-date-wins ordering
   - `tests/test_api_backup.py` (new) — endpoint auth requirement, 200 response shape for no-prior-backup / success / failed cases
7. [x] **Documentation Generation**: created `aidlc-docs/construction/api-service/code/backup-summary.md`

## Verification (not deferred to Build & Test — done now, live)

- [x] Ran the full `api-service` unit test suite against a real disposable Postgres (testcontainers): 113/113 passing, zero regressions
- [x] OpenAPI schema smoke-tested: `/backups/status` present with expected operation shape
