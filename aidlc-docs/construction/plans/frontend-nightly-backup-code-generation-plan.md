# Code Generation Plan — Frontend SPA Unit — Nightly Transaction Backup

**Unit**: Frontend SPA (Unit 4). **Stories**: US-7.4.
**Dependencies**: API Service unit (`GET /backups/status`) — complete.

## Steps

1. [x] **API client**: `src/api/backup.ts` (new) — `getBackupStatus`; `src/api/types.ts` — `BackupStatusResponse`/`BackupOutcome`/`BackupFailureCategory`
2. [x] **Component**: `BackupStatusPanel`, added inline in `ReviewPage.tsx` (matching the existing convention — `ProposalTable`/`BulkActionBar` are also inline, not separate files), rendered above `ProposalTable`, visually separate per the requirements clarification
3. [x] **Unit Testing**: extended `tests/ReviewPage.test.tsx` — 5 new tests (no-backups-yet, success with count, drive-connectivity failure + reconnect link, generic failure, visual separation from the proposal table) plus a `beforeEach` default mock so existing tests are unaffected
4. [x] **Documentation Generation**: create `aidlc-docs/construction/frontend/code/backup-status-panel-summary.md`

## Verification (not deferred to Build & Test — done now, live)

- [x] Ran the full frontend suite: 68/68 passing (up from 51), zero regressions
- [x] Clean `tsc -b` type-check and `vite build` production build
