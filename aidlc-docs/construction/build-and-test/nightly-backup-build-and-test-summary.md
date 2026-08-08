# Build and Test Summary — Nightly Transaction Backup (Epic 7)

Scoped to this feature. The original `build-and-test-summary.md` and its sibling instruction files remain the project's general reference; this document covers what was specifically verified for this change.

## Build Status
- **Build Tool**: Docker Compose (v2)
- **Build Status**: Success — `api-service`, `ingestion-worker`, and `frontend` all rebuilt with the new code and reached `healthy` status (twice for `api-service` and `frontend`, after the mid-verification fixes below); `database`'s image is unchanged (schema ships via migration, not image rebuild)
- **Build Artifacts**: 3 rebuilt Docker images

## Test Execution Summary

### Unit Tests
- **Total new tests**: 41 (6 Database + 20 Ingestion Worker + 8 API Service + 5 Frontend + 2 Frontend regression coverage for the reconnect-button fix)
- **Full suite results after this feature**: Database 24/24, Ingestion Worker 133/133, API Service 113/113, Frontend 70/70 — all passing, zero regressions
- **Status**: Pass

### Migration Verification (beyond unit tests)
- `alembic upgrade head` run against a real, separate disposable Postgres container. Caught a **pre-existing, out-of-scope bug**: migration 0005 (`ingestion_run_cancellation`, unrelated to this feature) fails against a genuinely fresh database, because migration 0001's table-scoping doesn't protect against columns added to an already-scoped table. Does not affect the live project database (already past 0005 historically). Flagged as a separate background task (not fixed here, per this project's established practice for out-of-scope findings) — worked around for verification purposes only (schema via `create_all()` + `alembic stamp 0005`) to test migration 0006 in isolation.
- Verified: table shape + BR-17/BR-18 constraints via `psql \d`, `alembic downgrade` fully removes the table and both enum types, re-running `upgrade head` twice is a safe no-op.
- **Live database**: migration `0006` applied cleanly to the actual running project database — `alembic_version` confirmed at `0006`.

### Integration / End-to-End Tests — Live, Against the Real Google Drive Account
Per explicit user confirmation (this is the first feature that writes to/deletes from the real Drive account, not just reads), verification was done live against the actual connected Drive account and the actual dedicated backup folder — not mocked.

- **Real backup run**: the live `ingestion-worker`'s own catch-up logic (WR-11/FR-8, working exactly as designed) triggered a real backup on its own on the very first poll cycle after redeploy. Confirmed the resulting `backup_runs` row and, separately, confirmed the actual CSV file's existence in the actual Drive backup folder via a direct live query.
- **Real retention test**: uploaded 8 additional real dummy backup-named files (distinct real Drive `createdTime`s) to bring the folder to 9 files, ran `_enforce_retention` for real, confirmed exactly 7 remained and the 2 oldest were genuinely deleted from Drive.
- **API layer**: minted a real JWT via the app's own signing code (same approach as Epic 6 — not a bypass of any security control, just avoids needing the account owner's actual password) and confirmed `GET /backups/status` against the live running API reflected the live `backup_runs` row correctly.
- **Frontend, real browser session**: logged into the actual running app, navigated to `/review`, confirmed the Backup Status panel rendered real data ("Last backup succeeded at 08/08/2026, 15:33:46 (6142 transactions)"), visually separate from the (empty) proposal table below it, exactly as designed.
- **Cleanup**: deleted all test-created files from the real Drive backup folder and the test `backup_runs` DB row afterward, restoring a genuinely clean state so the real nightly schedule (and the natural due-check on the next poll cycle) takes over on its own — the final backup visible in the system after this session is a real, legitimate automatic run, not a leftover test artifact.

### Two Real Bugs Found and Fixed During Live Verification

**1. Drive OAuth scope too narrow for the new write/delete calls.** The stored refresh token was granted under `drive.readonly` (a deliberate least-privilege choice from when the app only ever read PDFs) — genuinely can't be used for writes no matter what the backup code does, since scope is fixed at grant time. First live attempt failed with a real `403 insufficientPermissions`. Fixed by broadening `drive_connect/service.py`'s `SCOPES` to the full `https://www.googleapis.com/auth/drive` (`drive.file` was considered but doesn't reliably cover writing into an arbitrary externally-shared folder ID the app didn't create itself — the same "arbitrary folder by ID" pattern `drive.readonly` already relies on for reading the ingestion source folder). Required the user to re-grant OAuth consent (cannot be done on the user's behalf per this project's operating rules).

**2. No UI path existed to actually re-grant consent.** `SettingsPage.tsx`'s `DriveConnectionCard` only rendered the "Connect Google Drive" button when `!status.connected` — since the old, narrower-scope credential already counted as "connected," there was no button for the user to click at all, regardless of intent. Confirmed via the DB (`oauth_credentials.updated_at` unchanged) and API logs (zero `/drive/connect` hits) after the user's first attempt. Fixed generally, not as a one-off patch: the button is now always shown, relabeled "Reconnect Google Drive" when already connected, so any future scope change has a working path back into the flow too. Added `SettingsPage.test.tsx` (previously zero coverage for this page) proving both label states. Verified fixed live: the user's second attempt showed real `/drive/connect` and `/drive/callback` hits in the API logs with `scope=https://www.googleapis.com/auth/drive`, and `oauth_credentials.updated_at` advanced to the current time.

### Performance / Security / Contract Tests
- **Performance**: N/A, same rationale as the base project (no performance NFR target for a single-user personal app)
- **Security**: N/A, Security Baseline extension opted out at the original Requirements Analysis; this feature's OAuth scope broadening is a necessity of the feature itself, not new secret-handling surface
- **Contract**: Frontend `types.ts` DTOs hand-kept in sync with the new Pydantic schemas, verified by `tsc` passing and by the real browser session rendering real API responses correctly

## Overall Status
- **Build**: Success
- **All Tests**: Pass (340 unit tests across all 4 units — 24 Database + 133 Ingestion Worker + 113 API Service + 70 Frontend — plus live end-to-end verification against the real Drive account, including two real bugs found and fixed)
- **Ready for Operations**: Yes
