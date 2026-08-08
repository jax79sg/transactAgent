# Requirements: Nightly Transaction Backup to CSV

Tracked as a Post-Completion feature, same pattern as the Recategorization Review Panel (Epic 6). Base project status unchanged: COMPLETE. This document is feature-scoped and does not modify the original project-wide `requirements.md`.

## Intent Analysis

- **User Request** (verbatim): "I would like to do up a back up of the transactions on a nightly basis, with a retention of 7 days. The backup shall be in the form of csv files. The backup shall be saved in a 'backup' sub folder of the same google drive folder." (destination later revised — see FR-3 and Clarification 2 below)
- **Request Type**: New Feature
- **Scope Estimate**: Multiple Components — Database (new backup-run tracking table), Ingestion Worker Service (scheduling, CSV export, Drive upload/retention), API Service (expose backup status), Frontend SPA (new status panel on the Review page)
- **Complexity Estimate**: Moderate

## Requirements Depth
**Standard** — normal complexity, functional + non-functional requirements needed, clarified via two rounds of questions (`nightly-backup-questions.md`, `nightly-backup-clarification-questions.md`).

## Functional Requirements

- **FR-1**: The system exports a full snapshot of ALL transactions currently in the database to a CSV file once per calendar day (every run re-exports everything — not incremental).
- **FR-2**: The nightly schedule runs at a consistent, implementation-chosen time. **Default: 02:00 server/container local time** (documented assumption — low-traffic window, no conflict with the existing 5-second ingestion poll loop).
- **FR-3**: Backup CSV files are uploaded to a `backup` subfolder inside a **separate, dedicated Google Drive folder** (folder ID `1vb91lAVBH8lwniPbTz8xIdH6fkdu-f9t`), distinct from the source ingestion folder (`google_drive_folder_id`). This is a deliberate deviation from the original request ("same folder") to avoid the backup being lost if the source folder becomes unavailable. The `backup` subfolder is created automatically on first use if it does not already exist.
- **FR-4**: The connected Google Drive account (the single shared OAuth credential already used for ingestion — see `oauth_credentials` / `drive_client.py`) is confirmed to have edit access to the new backup folder; no additional OAuth flow is introduced.
- **FR-5**: Each backup file is named with a timestamp: `transactions-backup-<timestamp>.csv`. **Default format: `transactions-backup-YYYYMMDDTHHMMSSZ.csv`** (documented assumption — filesystem-safe, sorts chronologically by name).
- **FR-6**: CSV includes all columns of the `transactions` table as stored: `id`, `bank_statement_id`, `transaction_date`, `description`, `out_flow`, `in_flow`, `currency`, `bank_name`, `category_id`, `category_source`, `converted_amount_sgd`, `conversion_is_approximate`, `conversion_unavailable`, `fx_rate_used_id`, `created_at`, `updated_at` (documented assumption: raw columns/foreign-key IDs as-is, not human-readable joins — "All columns on the transactions table" was the explicit choice in Q2).
- **FR-7 (Retention)**: After each successful backup, the system keeps exactly the 7 most recent backup files in the `backup` subfolder and deletes any older ones. Deletion only ever targets files this system created in that subfolder — never arbitrary Drive content.
- **FR-8 (Missed-schedule catch-up)**: If the worker was offline at the scheduled time, it runs a catch-up backup as soon as it is back online — but only if today's backup has not already run — then resumes the normal nightly schedule.
- **FR-9 (Failure handling)**: On failure, the system does NOT auto-retry within the same night. It logs the failure and waits until the next scheduled night to try again.
- **FR-10 (Backup status tracking)**: Backup run history/status (success, failure, and failure reason/category) is persisted (survives worker restarts) so it can drive both FR-8's catch-up check and FR-11's frontend display.
- **FR-11 (Frontend visibility)**: The Review page (`/review`) displays a **"Backup Status" panel**, visually separate from the existing recategorization ProposalTable. This panel shows the outcome of the most recent backup attempt(s):
  - On a Drive-connectivity failure specifically: an indicator prompting the user to reconnect Google Drive (pointing to the existing Settings page connect flow).
  - On any other failure (e.g. a database error while building the CSV): a generic failure indicator, shown in the same panel.
  - (Success state display is implementation's discretion — at minimum, the panel should not show a stale/misleading failure state after a subsequent success.)

## Non-Functional Requirements

- **NFR-1**: Backup processing must not violate the existing "one run/job at a time" worker invariant (WR-8) — it must fit into the existing poll loop (`main.py: poll_once()`) without concurrently overlapping an active IngestionRun or RecategorizationJob processing step.
- **NFR-2**: Drive upload/list/delete calls reuse the existing transient-error retry pattern (`retry_with_backoff` / `TransientError` in `clients/retry.py`) already used by `drive_client.py`'s list/download functions — consistent resilience to transient Drive API errors within a single attempt (distinct from FR-9's no-next-day-early-retry rule, which governs retrying a whole failed backup attempt, not transient errors within one attempt).
- **NFR-3**: CSV export must scale with table growth (the table already holds thousands of rows) — query should not load the entire result set through inefficient patterns that wouldn't scale further; batched/streamed reads preferred over unnecessary intermediate structures if the ORM supports it cheaply.
- **NFR-4**: Retention deletion must be scoped and safe — only ever delete files that match this feature's own naming convention within the dedicated `backup` subfolder, never other content.

## Business Context

- **Goal**: Protect transaction data against loss, independent of the primary Drive folder used for statement ingestion.
- **Constraint surfaced during clarification**: Storing backups inside the same source folder was identified by the user as a single point of failure (losing the source folder would lose the backups too) — resolved by using a separate dedicated Drive folder (FR-3).
- **Success Criteria**: A backup CSV appears in the dedicated backup folder every day the worker is running (or on next catch-up if it wasn't), exactly 7 most-recent files are retained at all times, and any failure is visible to the user without needing to inspect worker logs.

## Documented Assumptions (flagged, not further questioned)
1. Nightly schedule time defaults to 02:00 server/container local time (FR-2).
2. Filename timestamp format: `transactions-backup-YYYYMMDDTHHMMSSZ.csv` (FR-5).
3. "All columns" (FR-6) means raw stored columns/FK IDs, not human-readable joined values (e.g. category name).
4. A new database entity (working name: `BackupRun`, analogous to the existing `IngestionRun`) will be introduced during Functional Design to persist backup history per FR-10 — exact shape deferred to Functional Design, not fixed here.

## Out of Scope
- Restoring from a backup (no restore/import feature requested or implied).
- Backing up any table other than `transactions`.
- Per-user Drive credentials (this app uses one shared OAuth credential; unaffected by this feature).
