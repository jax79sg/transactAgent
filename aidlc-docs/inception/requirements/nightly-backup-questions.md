# Nightly Transaction Backup — Clarifying Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference.

## Question 1 — Backup Content Scope
Each nightly backup CSV should contain:

A) A full snapshot of ALL transactions currently in the database (every run re-exports everything)

B) Only transactions added/changed since the previous backup (incremental)

C) Other (please describe after [Answer]: tag below)

[Answer]: A


## Question 2 — CSV Fields
Which transaction fields should be included in the CSV?

A) All columns on the `transactions` table (id, date, description, out_flow, in_flow, currency, bank_name, category, category_source, converted_amount_sgd, conversion flags, fx rate reference, timestamps, etc.)

B) A curated "user-facing" subset only (date, description, out_flow, in_flow, currency, bank_name, category, converted_amount_sgd) — matching what the Transactions page shows

C) Other (please describe after [Answer]: tag below)

[Answer]: A


## Question 3 — Backup Schedule Time
What time should the nightly backup run?

A) A fixed time you specify (e.g. 02:00 server time) — please give the exact time after [Answer]: if choosing this

B) No specific time requirement — any consistent nightly time chosen by the implementation is fine (e.g. 02:00 server/container time)

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 4 — File Naming Convention
How should each backup CSV file be named in the Drive `backup` subfolder?

A) `transactions-YYYY-MM-DD.csv` (one file per calendar day)

B) `transactions-backup-<timestamp>.csv` (includes time, not just date)

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 5 — Retention Behavior
"Retention of 7 days" means:

A) Always keep exactly the 7 most recent backup files in the `backup` folder, deleting older ones each night after a new backup succeeds

B) Delete any backup file older than 7 calendar days (regardless of how many files that leaves)

C) Other (please describe after [Answer]: tag below)

[Answer]:A


## Question 6 — Missed Backup Recovery
If the worker/container is down at the scheduled backup time (e.g. restarted, or was offline that night), what should happen?

A) Skip that night's backup entirely — resume normal nightly schedule when it's back up

B) Catch up and run a backup as soon as the worker is back online if today's backup hasn't run yet, then continue on schedule

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 7 — Failure Handling
If a nightly backup fails (e.g. Drive API error, Drive not connected), what should happen?

A) Log the failure and retry automatically on the next poll cycle until it succeeds or a new day starts

B) Log the failure only; wait for the next scheduled night to try again (no same-night retry)

C) Other (please describe after [Answer]: tag below)

[Answer]:Notify user to re-establish drive connectivity via the review tab.


## Question 8 — Visibility / Notification
Should backup status be visible anywhere, or is this a purely silent background operation?

A) Purely backend/silent — only visible in worker logs (matches how the ingestion run's Drive interactions are logged today)

B) Surface backup history/status somewhere in the frontend (e.g. a small status indicator or list of recent backups)

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 9 — Relationship to Existing Ingestion Runs
The `backup` subfolder will live inside the same Google Drive folder that's scanned for incoming bank-statement PDFs (`google_drive_folder_id`). Since ingestion only looks for `mimeType='application/pdf'`, CSV files in a `backup` subfolder won't be picked up as statements to ingest — confirming this is acceptable and no additional exclusion logic is needed beyond what already exists.

A) Confirmed — no additional exclusion logic needed

B) Other / additional concern (please describe after [Answer]: tag below)

[Answer]:B. Losing the folder loses the backup too. Let's store it in a seperate Google drive folder here. [redacted Drive folder URL -- see GOOGLE_DRIVE_BACKUP_FOLDER_ID in .env.example]  
