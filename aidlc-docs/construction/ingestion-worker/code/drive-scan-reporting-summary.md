# Drive scan reporting and no-activity statements: code summary

2026-11-16. Owner request after issue #70 was closed as an orphaned record. Rules: WR-70, WR-71 (`../functional-design/business-rules.md`); database BR-54. Plan: `../../plans/drive-scan-skips-and-no-activity-plan.md`.

## What changed

| Where | Change |
|---|---|
| `database/.../models.py`, `migrations/versions/0023_run_file_skip_reasons.py` | Outcomes `skipped_no_activity`, `skipped_not_a_pdf`; column `skip_reason`; CHECK requiring it for those two. Enum values are added inside `autocommit_block()` (as in 0020). `0001` drops `skip_reason` after its `create_all` so the chain builds from an empty database. |
| `clients/drive_client.py` | `list_folder_ignored_items` (the other half of the folder listing: `mimeType != 'application/pdf'`, not trashed, paged) returning `IgnoredItem(id, name, mime_type, reason)`; `describe_ignored_item` writes the reason (subfolder, shortcut, image, Google Doc/Sheet/Slides, other type). `list_folder_pdf_files` is untouched (the backfill also uses it). |
| `extraction/service.py` | New `NoActivity` result; returned for zero transactions when the bank and an account were identified, confidence meets the threshold, and the model returned no transactions at all (counted before the future-date drop). Everything else with zero transactions stays `ExtractionFailure("Zero transactions extracted")`. |
| `orchestrator/pipeline.py`, `repository.py` | Lists ignored items (best effort, never fatal), records each as `skipped_not_a_pdf` with its reason and writes a log line; `files_found` and `skipped` include them. A `NoActivity` file is recorded as `skipped_no_activity` with the standing `NO_ACTIVITY_REASON`, counts as skipped, creates nothing. `record_run_file` takes `skip_reason`. |
| `backfill/check_extraction.py` | Treats `NoActivity` like a failed comparison (reported, not raised). |
| API `ingestion/schemas.py`, `router.py` | `RunFileDetail.skipReason`. |
| Frontend `api/types.ts`, `pages/IngestionPage.tsx` | Two new outcome values and `skipReason`; the Reason column falls back to it; a notice says how many items were not read. |

## Decisions worth knowing

- **Not remembered.** A no-activity file is read again next run (one Gemini call each, as the failed ones were). Remembering would turn a one-off bad read into a permanent one; left for the owner to decide.
- **A quiet account is told apart from a bad read** by what the model positively found (an account) and by transactions that were seen and then discarded, not by the count alone.
- **No release or guide change here**: the user guide and version belong to the release.

## Tests

Database 273 (+5), worker 774 (+23: listing, extraction rule and its must-stay-failure cases, pipeline counts and statuses, the next-run re-read, the backfill checker), API 739 (+2), frontend 687 (+5, from a clean `npm ci`). Ten deliberate breakages (seven in the worker, the database CHECK, two in the frontend) each made a test fail. The migration was run end to end on a throwaway Postgres: from empty to head, downgrade to 0022, upgrade again.
