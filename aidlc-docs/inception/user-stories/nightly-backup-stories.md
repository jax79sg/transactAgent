# User Stories — Nightly Transaction Backup

Appends **Epic 7** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6), kept in a separate file so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity**: Coarse, epic-level capability stories — matches the existing convention.
**Acceptance Criteria**: Given/When/Then happy path plus explicit edge-case scenarios — matches the existing convention.
**Traceability**: Each story references `nightly-backup-requirements.md`'s FR/NFR IDs.

---

## Epic 7: Nightly Transaction Backup

### US-7.1: Automatic nightly backup of all transactions
**As** the Account Owner, **I want** all of my transactions automatically exported to a CSV file and uploaded to a dedicated backup location in Google Drive every night **so that** my transaction history is protected without me having to do anything manually.

**Traces to**: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6

**Acceptance Criteria**:
- *Happy path*: Given the scheduled backup time is reached, When the backup runs, Then a CSV containing every transaction currently in the database is generated and uploaded to the `backup` subfolder of the dedicated backup Google Drive folder (separate from the statement-ingestion source folder), with a timestamped filename.
- *Edge case — backup folder doesn't exist yet*: Given the `backup` subfolder does not yet exist inside the dedicated backup Drive folder, When the first backup runs, Then the subfolder is created automatically before the file is uploaded.
- *Edge case — only once per day*: Given a backup already ran successfully today, When the scheduled time is reached again the same day, Then no duplicate backup is triggered.
- *Edge case — doesn't disturb ingestion*: Given a statement ingestion run or recategorization job is in progress, When the scheduled backup time arrives, Then the backup does not run concurrently with it — it fits into the same one-at-a-time processing pattern the worker already uses.

### US-7.2: Only the most recent week of backups is kept
**As** the Account Owner, **I want** only the 7 most recent nightly backups kept in Drive **so that** I always have a recent safety net without backup files accumulating forever.

**Traces to**: FR-7, NFR-4

**Acceptance Criteria**:
- *Happy path*: Given a new backup uploads successfully and more than 7 backup files now exist in the `backup` subfolder, When retention cleanup runs, Then only the 7 most recent files remain — the oldest excess files are deleted.
- *Edge case — fewer than 7 exist*: Given fewer than 7 backup files exist, When retention cleanup runs, Then nothing is deleted.
- *Edge case — never touches unrelated files*: Given other files exist in the `backup` subfolder that weren't created by this feature (e.g. a file a user manually placed there), When retention cleanup runs, Then those files are never deleted — only files matching this feature's own backup naming convention are eligible for deletion.

### US-7.3: A missed backup catches up automatically
**As** the Account Owner, **I want** a backup that was missed because the system was offline to run as soon as it's back **so that** a restart or outage doesn't silently create a gap in my backup history.

**Traces to**: FR-8

**Acceptance Criteria**:
- *Happy path*: Given the worker was offline at last night's scheduled backup time and today's backup has not yet run, When the worker starts back up, Then it runs a catch-up backup immediately, then resumes the normal nightly schedule.
- *Edge case — no double backup*: Given today's backup already ran successfully before the worker restarted, When the worker starts back up, Then no redundant catch-up backup is triggered.

### US-7.4: I can tell when a backup failed, without reading logs
**As** the Account Owner, **I want** to see when a nightly backup failed, and be told to reconnect Google Drive if that's the cause **so that** I can fix the problem before I lose more than one night's protection, without having to inspect worker logs.

**Traces to**: FR-9, FR-10, FR-11

**Acceptance Criteria**:
- *Happy path — Drive-connectivity failure*: Given a backup fails because Google Drive is not connected or the connection is no longer valid, When I open the Review page, Then a "Backup Status" panel (separate from the recategorization proposal table) shows an indicator prompting me to reconnect Google Drive.
- *Happy path — other failure*: Given a backup fails for a reason unrelated to Drive connectivity (e.g. a database error while building the CSV), When I open the Review page, Then the same Backup Status panel shows a generic failure indicator, not the Drive-reconnect-specific message.
- *Edge case — no same-night retry*: Given a backup fails, When the next poll cycle runs later the same night, Then the system does not automatically retry — it waits for the next scheduled night.
- *Edge case — status clears on success*: Given a previous backup failed and the next scheduled (or catch-up) backup succeeds, When I open the Review page, Then the Backup Status panel no longer shows the stale failure indicator.
