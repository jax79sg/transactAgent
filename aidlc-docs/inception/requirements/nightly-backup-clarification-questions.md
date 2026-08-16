# Nightly Transaction Backup — Follow-Up Clarification Questions

Your answers to Q7 and Q9 introduced specifics that need one more round of clarification before requirements can be finalized.

## Clarification 1: Failure Handling — Retry vs. Notify (from Q7)
You answered Q7 with a custom response: "Notify user to re-establish drive connectivity via the review tab." The original options were (A) auto-retry on next poll cycle until success or day-end, or (B) log only and wait for the next scheduled night. Your answer doesn't specify which of these still applies alongside the notification.

Also, I checked the frontend: there is no "review tab" concept for Drive connectivity today. The existing "Review" page (`/review`) is for recategorization proposals (Epic 6) and has nothing to do with Drive. The actual Drive connect/reconnect UI ("Google Drive: Connected / Not connected" + "Connect Google Drive" button) lives on the **Settings** page (`/settings`), driven by `getDriveStatus()`.

### Clarification Question 1a — Retry Behavior
When a nightly backup fails, should the system also keep auto-retrying?

A) Auto-retry on every poll cycle until it succeeds or the day ends, AND show a notification if it's a Drive-connectivity failure specifically

B) Do NOT auto-retry — log the failure, show the notification, and just wait for tomorrow's scheduled backup

C) Other (please describe after [Answer]: tag below)

[Answer]:B

### Clarification Question 1b — Notification Location
Where should this "please reconnect Google Drive" notification appear?

A) On the existing Settings page (`/settings`), where the Drive connect/reconnect UI already lives — e.g. a warning banner near the "Google Drive" card

B) Somewhere else — please describe after [Answer]: tag below

[Answer]:B, in the review tab, as a seperate panel from the transaction review.

### Clarification Question 1c — Non-Drive Failures
Q7's answer specifically covers Drive-connectivity failures. If a backup fails for a different reason (e.g. a database error while building the CSV, not a Drive issue), should the same "reconnect Drive" notification apply, or should it be a different/generic failure indicator (or no frontend indicator at all)?

A) Generic failure indicator (not specifically "reconnect Drive" wording) shown in the same place

B) No frontend indicator for non-Drive failures — log only

C) Other (please describe after [Answer]: tag below)

[Answer]:C. in the review tab, as a seperate panel from the transaction reviews.


## Clarification 2: Separate Backup Folder — Structure and Access (from Q9)
You provided a separate Google Drive folder for backups (folder ID redacted here -- set via `GOOGLE_DRIVE_BACKUP_FOLDER_ID`, see `.env.example`), replacing the original "backup subfolder of the same source folder" idea, to avoid a single point of failure if the source folder is ever lost.

### Clarification Question 2a — Subfolder or Root
Within that separate folder, should backup CSVs be:

A) Written directly into that folder's root (no further subfolder)

B) Written into a `backup` subfolder created inside that separate folder (keeps the same subfolder structure, just relocated)

C) Other (please describe after [Answer]: tag below)

[Answer]:B

### Clarification Question 2b — Access Confirmation
The app currently authenticates to Google Drive using a single shared OAuth credential (the one connected via Settings → "Connect Google Drive"). For uploads to succeed, that same connected Google account needs write access to the folder you shared.

A) Confirmed — the connected Google account already has (or will be given) edit access to that folder

B) Not sure / needs to be set up — please describe after [Answer]: tag below

[Answer]: A
