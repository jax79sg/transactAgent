# BackupStatusPanel — Code Summary (Epic 7, Nightly Transaction Backup)

New: [`src/api/backup.ts`](../../../../frontend/src/api/backup.ts) (`getBackupStatus`), `BackupStatusResponse`/`BackupOutcome`/`BackupFailureCategory` added to `src/api/types.ts`.

`BackupStatusPanel` is defined inline in [`ReviewPage.tsx`](../../../../frontend/src/pages/ReviewPage.tsx), matching the existing convention (`ProposalTable`/`BulkActionBar` are also inline, not separate component files) — rendered above `ProposalTable`, its own bordered section (`data-testid="backup-status-panel"`).

## Three display states (driven by `BackupStatusResponse.outcome`, AR-14)

| State | Test ID | Content |
|---|---|---|
| No backup yet (`outcome === null`) | `backup-status-none` | "No backups yet." |
| Success | `backup-status-success` | Last backup time + transaction count |
| Failed, Drive connectivity | `backup-status-failed-drive` | Prompt to reconnect, linking to `/settings` |
| Failed, other | `backup-status-failed-other` | Generic "Last backup failed." |

Polls every 5 minutes (`BACKUP_STATUS_POLL_INTERVAL_MS`) — looser than `PendingReviewBadge`'s 30s since a backup outcome changes at most once a night.

## Tests

`tests/ReviewPage.test.tsx`: 5 new tests under a `BackupStatusPanel` describe block, plus a `beforeEach` default mock (`getBackupStatus` mocked globally) so the panel's own network call doesn't affect pre-existing tests that don't care about it.

Full suite: 68/68 passing. Clean `tsc -b` type-check and `vite build`.
