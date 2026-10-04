# Probable Duplicate Statement Detection — Ingestion Worker Code Summary (Epic 14)

Design: `../functional-design/` (WR-57..WR-69) and the Database design (BR-39..BR-53). Plan: `aidlc-docs/construction/plans/ingestion-worker-probable-duplicate-code-generation-plan.md`.

## What was built

| Area | Where | What |
|---|---|---|
| Settings | `config.py` | `duplicate_detection_enabled` (default **off**), `duplicate_match_ratio` (0.80, bounded 0.50 to 1.00), `duplicate_min_transactions` (3, bounded 1 to 50); a value out of range stops startup (WR-57) |
| The matching rule | `duplicates/matching.py` | **Pure**: no database, network or clock. One-to-one matching on date, amount, direction, currency and description (equal after normalization, else similarity at or above 0.85), ratio against the smaller side, period overlap, the account rule, the small-statement gate, the size relation (Question 1 = C), the reason text, the 10-row snapshot, and the kept-copy rule |
| Persistence | `duplicates/repository.py` | Held statements as matcher inputs (transactions, account facts, file name from the processing run file), manual-correction counts, remembered files, comparisons, pairs, scan state |
| Detector | `duplicates/service.py` | `find_probable_duplicate_of` (check 2, read-only), `record_skipped_duplicate`, `compute_findings` (read-only, with near misses), `is_pair_scan_due_now`, `run_pair_scan` |
| Check 1 and check 2 | `duplicate_detection/service.py`, `orchestrator/pipeline.py` | `lookup_remembered_file` before extraction (always on); the probable-duplicate check after extraction and before any account is created, inside a savepoint, **failing open**; `process_run(..., backfill_mode=)` |
| Removal | `duplicates/removal.py`, `duplicates/cascade.py` | Claim, re-verify (WR-66), delete + remembered file + pair + job move in **one savepoint-guarded transaction**, then embeddings with 5 attempts and waits of 1, 2, 4, 8 s, parking as `embeddings_failed`; `cascade.delete_statements` is the one delete implementation, now also used by the backfill's wipe |
| Vector store | `embedding/vector_store.py` | `delete_embeddings` |
| Poll loop | `main.py` | Seven branches: removal third, pair scan sixth; startup recovery fails stale `running` removal jobs |
| Backfill | `backfill/duplicates.py` and edits to `service.py`, `corrections.py`, `restore.py`, `report.py`, `tables.py`, `__main__.py` | `check-duplicates`; dry run lists the pairs it will skip; pre-registration of the copy to skip; the reingest in `backfill_mode`; corrections carried from a skipped copy; report sections; backup and restore of the four mutable tables; pre-flight refusal during a removal |
| Deployment | `docker-compose.yml`, `.env.example` | The three settings are passed to **both** the worker and the API containers (the same mapping every worker setting has) |

## How it was tested

**664 Ingestion Worker tests pass** (467 existing + 197 new), and `ruff check src tests` is clean. The 467 existing tests pass without modification except `test_main_loop.py`, which gained one autouse fixture (see findings). New: `test_duplicates_matching.py` (60, including the property-based tests), `test_duplicates_service.py` (39), `test_duplicates_removal.py` (20), `test_duplicates_cascade.py` (6), `test_backfill_duplicates.py` (20), `test_duplicates_end_to_end.py` (2), plus additions to the config, pipeline, poll-loop, vector-store and duplicate-detection tests.

**Property-based tests** (hypothesis): matching is symmetric in its arguments and bounded by both sides; a list matches itself completely; the verdict is symmetric and its ratio is within 0 to 1; the snapshot has at most 10 rows, they are the largest, ties earlier date first; the kept copy ignores argument order.

**The two real-data shapes** are used throughout: the UOB June pair (corrections on the earlier copy, so it is kept) and the Trust June pair (two spellings of the bank, corrections on the **later** copy, which is kept), and the CIMB one-transaction look-alikes (never flagged, reported as near misses with the reason).

**End to end, through the real pipeline, scan and handler**: two downloads of one statement are ingested as they are today (detection off) and counted twice; detection is switched on; the scan finds the pair; a confirmed removal deletes the duplicate, its dependents and exactly its transactions' embeddings; the next ingestion run recognises the removed copy's file from memory and does **not** call extraction; and overriding the removed copy brings it back on the following run.

**Mutation check** (a scratch copy of the code, one deliberate defect at a time; every one made a test fail): a transaction allowed to match twice; the small-statement gate removed; the fail-open wrapper removed; the "the statement to keep still exists" re-verification removed; the delete and its bookkeeping no longer one transaction; the kept copy's own corrections no longer winning a conflict; the remembered-file check made dependent on the detection switch.

## Findings made while building and testing (not visible from the design alone)

1. **Floating point would have rejected an exact match.** `0.7 * 10` is `7.000000000000001`, so 7 of 10 would have failed a 0.70 threshold. The comparison is done in `Decimal` (and a test pins it).
2. **A greedy fuzzy pairing is not symmetric.** Pairing similar descriptions best-first makes the matched count depend on which statement is passed first when scores tie. The fuzzy remainder is therefore a maximum bipartite matching (equal descriptions are paired first; they are interchangeable, so that cannot change the count). A test shows greedy pairing finds one pair where the maximum finds two.
3. **Hypothesis found an input that is not real**: two different statements with the same content hash and timestamp. Hashes are unique (BR-3), so the property assumes distinct hashes; the function was not changed.
4. **The test fixture's rollback undoes the whole test transaction.** A test that asserted "the statements are still there after the wipe rolled back" could not hold; it now proves the real property (pre-registration, the wipe and the rollback happen in one transaction with no commit between) by the order of events.
5. **A mocked database session looks like a pending removal.** `MagicMock().scalar(...)` is truthy, so every existing poll-loop test would have entered the new removal branch. The existing tests got one autouse fixture that makes the two new branches find nothing; the new tests override it.
6. **Refinements to the Functional Design, recorded as dated notes there** (WR-63, WR-65, WR-69): the pair scan supersedes a pending pair that is **no longer found** for any reason (a statement gone, a file overridden, or no longer flagged under changed settings), not only when a statement is gone; a failing removal or scan in `poll_once` is logged and the cycle **carries on** to the later branches instead of returning; and the backfill pre-registers **before** the wipe, in the wipe's transaction, rather than just before the reingest, so it is atomic with the wipe and survives an interrupted run.

## Operator notes

- **Accuracy check (NFR-PD-1), before switching detection on:** `python -m ingestion_worker.backfill check-duplicates` (through `docker compose`, like the other backfill commands). It is read-only (no Drive, no Gemini) and prints each flagged pair, the copy it would keep, whether removal is offered, the corrections on each, and every near miss with the reason it was not flagged. Both June pairs should be flagged and the CIMB look-alikes should appear as near misses. **Starting the tool applies pending database migrations** (as every backfill command does), so on the live database that is a change, not only a read.
- **The backfill** applies the rule whatever the switch says, skips the right copy of each same-size pair, re-ingests both statements of a different-size pair (listed for the Review panel), carries corrections from a skipped copy to the kept one (the kept copy's own corrections win a conflict), and asks the worker for a pair scan when `finish` completes.
- **Switching detection on** is a setting change (Settings page or `.env`) that takes effect when the worker restarts; the worker then scans the stored statements automatically and the Review panel lists what it finds.
