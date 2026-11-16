# Drive scan reports what it skips; zero-activity statements stop counting as failures

2026-11-16. Owner request (after issue #70 was closed as an orphaned record): "I want the Drive scan to both report what it skips, and zero-activity statements to stop counting as failures."

## What is true today

- The scan (`clients/drive_client.list_folder_pdf_files`) asks Drive for `mimeType='application/pdf'` children of one folder. Subfolders, shortcuts, images and Google-native documents are never listed, so a statement kept in any of them is invisible and nothing says so.
- A statement whose extraction finds no transactions at all fails with "Zero transactions extracted" (WR-1c). On the owner's live folder that was 23 of 251 files on the last run, every one an account with no activity that month, so every run ended `completed_with_failures` although nothing was wrong. They are re-read (one Gemini call each) on every run, because a failed file leaves no statement behind to be skipped as a duplicate.

## Decisions

1. **Ignored items are listed and recorded, never fatal.** A second Drive query (`mimeType != 'application/pdf'`, same folder, not trashed) lists what the scan does not read; each item becomes a run file with the new outcome `skipped_not_a_pdf` and a reason that says why (subfolder, shortcut, other file type). They count in `files_found_count` and `files_skipped_count`, so found = processed + skipped + failed still holds. If this extra query fails, a warning is logged and the run goes on: reporting must never stop ingestion.
2. **No activity is a new outcome, not a failure.** Zero transactions across the whole statement is `skipped_no_activity` (counted as skipped, run ends `completed`) when the extractor identified the bank, found at least one account section with an account identifier, and its confidence meets the threshold. Zero transactions without that (no account found, or low confidence) stays a failure, exactly as before, because that is what a bad read looks like.
3. **Not remembered.** A no-activity file is still read again on the next run (as the failed ones were). Remembering it would turn a one-off extraction miss into a permanent one; it is listed as a follow-up for the owner to decide.
4. **A reason column.** `ingestion_run_files.skip_reason` (nullable text) carries the explanation for the two new outcomes; `failure_reason` keeps meaning failure.
5. **No change to what a statement with no activity creates**: nothing (no statement, account or balance), as before.

## Steps (tests first; tick as done)

- [x] 1. Database: enum values `skipped_no_activity`, `skipped_not_a_pdf`; column `skip_reason`; migration 0023 and its test.
- [x] 2. Worker: `drive_client.list_folder_ignored_items` and `describe_ignored_item`; tests.
- [x] 3. Worker: extraction returns `NoActivity` under the rule in decision 2; tests, including the cases that must stay failures.
- [x] 4. Worker: pipeline records ignored items (best effort) and no-activity files; run status is `completed` when nothing failed; tests.
- [x] 5. Worker: backfill `check_extraction` understands `NoActivity`; test.
- [x] 6. API: `skipReason` on the run-file DTO; test.
- [x] 7. Frontend: types, Reason column shows the skip reason, notice listing what the scan ignored; tests.
- [x] 8. Amend the approved design documents and code summaries in place (WR-1c, new rules, BR for the outcomes).
- [x] 9. Run every suite and lint; confirm the new tests fail without the change.
- [ ] 10. PR, bind, no merge. Guide text and version are part of the release, not this PR.
