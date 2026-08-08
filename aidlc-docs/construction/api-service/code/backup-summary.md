# Backup Status — Code Summary (Epic 7, Nightly Transaction Backup)

New module: [`api_service/backup/`](../../../../api-service/src/api_service/backup/).

| File | Purpose |
|---|---|
| `repository.py` | `get_latest_backup_run` — most recent `BackupRun` row by `backup_date` |
| `service.py` | `get_latest_backup_status` — maps to `BackupStatusResponse`, AR-14's null-fields no-prior-backup case |
| `schemas.py` | `BackupStatusResponse` (CamelModel) |
| `router.py` | `GET /backups/status`, auth-protected |

## Key implementation decisions

- **Read-only, no write path**: unlike every other component in this service, Backup Status never creates/updates/deletes anything — `BackupRun` rows are written exclusively by the Ingestion Worker Service's Backup Manager. This mirrors Recategorization Review's "no direct call to the worker" rule.
- **No-prior-backup is not an error** (AR-14): `GET /backups/status` returns `200` with every field `null` when no `BackupRun` row exists yet, rather than `404` — an empty result is an expected state, not a failure.

## Tests

- `tests/test_backup_service.py` (new): 4 tests
- `tests/test_api_backup.py` (new): 4 tests (auth requirement + 3 response-shape scenarios)

Full suite: 113/113 passing. OpenAPI schema smoke-tested (`/backups/status` present with expected operation shape).
