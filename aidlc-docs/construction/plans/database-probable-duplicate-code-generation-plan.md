# Code Generation Plan — Database Unit — Probable Duplicate Statement Detection (Epic 14)

**This plan is the single source of truth for Database-unit Code Generation of this feature.**

**Unit**: Database (Unit 1). **Stories**: US-14.1 to US-14.7 at the schema layer only (business logic lives in Units 2 and 3, which own the application-layer rules named in the contract at the end). **Design source**: `aidlc-docs/construction/database/functional-design/` (BR-39..BR-52) and `database-probable-duplicate-functional-design-plan.md`.
**Dependencies**: none (first unit in the package sequence). Units 2 (API Service) and 3 (Ingestion Worker) depend on this one and are not started until it is approved.
**Database entities owned by this unit**: `KnownFile`, `DuplicateComparison`, `DuplicateComparisonRow`, `DuplicatePair`, `StatementRemovalJob`, `DuplicateScanState` (all new); plus a new outcome value and a new nullable link on `IngestionRunFile`.
**Code location**: workspace root, `database/` (existing structure; files are modified in place, never copied). Documentation: `aidlc-docs/construction/database/code/` (markdown only).
**Branch and delivery**: work continues on the existing local branch `feature/account-balance` (decision 2026-10-03: one PR for Epics 13 and 14). Nothing is committed or pushed.

## Approach notes (stated up front, since each differs from a simple reading of the design)

1. **Migration number**: `0020_probable_duplicates.py`, revision `0020`, down-revision `0019`. Migration 0019 (Account Balance) has not reached any real database, but unlike its earlier rework this is a separate feature in the same PR, so it gets its own revision.
2. **The new enum value needs its own commit.** `ingestionrunfileoutcome` gains `skipped_probable_duplicate`. PostgreSQL does not let a value added in a transaction be used in that same transaction, and this migration's `CHECK` constraints on `ingestion_run_files` mention it. So the migration adds the value inside Alembic's `autocommit_block()` first (committing the value), then everything else. If `autocommit_block()` does not behave under this project's `env.py` (which uses one transaction for the whole run), the fallback is to write those two `CHECK`s with `outcome::text`, which never touches the new enum value; this is settled by the live check in Step 7. Precedent for the value itself: migration 0005 (`ADD VALUE IF NOT EXISTS`).
3. **Migration 0001 needs the same fresh-database fix as for Epic 13.** 0001 creates `ingestion_run_files` from the *current* model, which will now carry a foreign key to `duplicate_comparisons` and the new enum value. On an empty database this would fail or leave things 0020 expects to create. 0001 therefore creates `duplicate_comparisons` temporarily, drops the `duplicate_comparison_id` column (which also drops its foreign key and the constraint that mentions it), drops the second `CHECK` by name (it names only existing columns, so dropping the column would leave it behind and 0020 would then find it already existing), and drops the temporary table, so 0020 stays the single source of truth. The unit tests build the schema straight from the models and cannot see this, so it is verified live (Step 7).
4. **Constraints are declared on the models**, not in raw SQL, wherever SQLAlchemy can express them (the approach settled for BR-30), so the unit tests exercise the real constraints and `create_all` and the migration produce the same schema. This includes the partial unique index for BR-45 (`postgresql_where`) and the hash-ordering `CHECK` for BR-43.
5. **Hash ordering uses `COLLATE "C"`** in its `CHECK`, so the database and Python agree on which of the two hashes is smaller whatever the server's locale (the hashes are lowercase hex, so this is belt and braces, but a mismatch would make the application's canonical order disagree with the constraint).
6. **JSON and array columns.** `removed_transaction_ids` is a PostgreSQL array of UUIDs and `deleted_counts` is `JSONB`. These are the project's first of each. Both are audit data written once and never queried by value; `deleted_counts` keys follow BR-51's dependents list, which may grow, so a fixed set of integer columns would need a schema change each time. The comparison rows are a table (not JSON) because there the database must enforce a bound. The Backfill Tool's `to_jsonb` / `jsonb_populate_recordset` backup round-trips both types, which Step 7 confirms.
7. **Property-based testing does not apply** to this unit (no pure functions), the same note as the rest of `test_models.py`.

## Steps

1. [x] **Branch**: confirm the working branch is `feature/account-balance` (no new branch; one PR, decided 2026-10-03). Nothing is committed or pushed; unrelated uncommitted changes already in the working tree stay untouched.
2. [x] **Business Logic Generation**: N/A for this unit (schema and constraints only; business logic lives in Units 2 and 3).
3. [x] **Repository Layer Generation**: N/A (each of Units 2 and 3 owns its data access against this schema).
4. [x] **Models** — modify `database/src/transactagent_db/models.py`:
   - extend `IngestionRunFileOutcome` with `SKIPPED_PROBABLE_DUPLICATE = "skipped_probable_duplicate"`; add enums `KnownFileState` (`probable_duplicate`, `overridden`, `confirmed_duplicate`), `DuplicatePairStatus` (`pending`, `dismissed`, `removed`, `superseded`), `StatementRemovalJobStatus` (`queued`, `running`, `embeddings_pending`, `embeddings_failed`, `completed`, `failed`), `ComparisonSide` (`earlier`, `later`), `ComparisonRowMarker` (`also_on_other`, `only_on_this_one`);
   - add `DuplicateComparison` (`duplicate_comparisons`): `id`; for each of `earlier_` and `later_`: `content_hash` (64), `file_name` (500, nullable), `bank_name` (255, nullable), `period_start`, `period_end`, `transaction_count`; `matched_count`; `match_ratio` (`Numeric(5,4)`); `reason` (text); `created_at`. `CHECK`s (BR-42): both counts at least 0; `matched_count` between 0 and the smaller of the two counts; `match_ratio` between 0 and 1. A `rows` relationship to its rows;
   - add `DuplicateComparisonRow` (`duplicate_comparison_rows`): `id`; `comparison_id` (FK to `duplicate_comparisons`, `ON DELETE CASCADE`); `side`; `rank`; `transaction_date`; `description`; `out_flow` / `in_flow` (`MONEY`, nullable); `currency` (3); `marker`. `CHECK`s (BR-42): exactly one flow set and positive (BR-2's form); `rank` between 1 and 10. `UNIQUE (comparison_id, side, rank)`;
   - add `KnownFile` (`known_files`): `id`; `pdf_content_hash` (64, **unique**, BR-39); `state`; `matched_statement_hash` (64, not null); `comparison_id` (FK, `ON DELETE RESTRICT`, not null); `created_at`; `updated_at`; `decided_at` (nullable). `CHECK` that the matched hash differs from the file's own (BR-40). Index on `comparison_id`;
   - add `DuplicatePair` (`duplicate_pairs`): `id`; `hash_a`, `hash_b` (64); `comparison_id` (FK, `RESTRICT`, not null); `keep_hash` (64); `status` (default `pending`); `found_at`; `decided_at` (nullable). `CHECK`s (BR-43): `hash_a COLLATE "C" < hash_b COLLATE "C"`; `keep_hash` is `hash_a` or `hash_b`. `UNIQUE (hash_a, hash_b)`. Indexes on `status` and `comparison_id`;
   - add `StatementRemovalJob` (`statement_removal_jobs`): `id`; `pair_id` (FK to `duplicate_pairs`, `RESTRICT`, not null); `remove_statement_hash` (64); `corrections_acknowledged` (default 0); `status` (default `queued`); `failure_reason` (text, nullable); `removed_transaction_ids` (array of UUID, nullable, **no foreign key**); `deleted_counts` (`JSONB`, nullable); `embedding_attempts` (default 0); `requested_at`; `started_at`; `finished_at`. `CHECK`s: `embeddings_pending` / `embeddings_failed` require `removed_transaction_ids` (BR-46); `failed` / `embeddings_failed` require `failure_reason` (BR-46); the two counts are at least 0. A **partial unique index** on `pair_id` where `status` is `queued`, `running`, or `embeddings_pending` (BR-45). Indexes on `status` and `pair_id`;
   - add `DuplicateScanState` (`duplicate_scan_state`): `id` (small integer primary key, default 1) with `CHECK (id = 1)` (BR-48); `last_scan_started_at`, `last_scan_completed_at`, `last_scan_match_ratio` (`Numeric(5,4)`), `last_scan_min_transactions`, `last_scan_pairs_found`, `recheck_requested_at` (all nullable);
   - modify `IngestionRunFile`: add `duplicate_comparison_id` (FK to `duplicate_comparisons`, `RESTRICT`, nullable) with an index, and two `CHECK`s (BR-49): `(outcome = 'skipped_probable_duplicate') = (duplicate_comparison_id IS NOT NULL)`, and a skipped-probable-duplicate row has no `bank_statement_id`;
   - none of the six new tables gets a foreign key to `bank_statements`, `statement_accounts`, or `transactions` (BR-50);
   - update the module docstring's list of application-layer-enforced rules to include BR-41, BR-44, the ordering half of BR-46, BR-47, BR-52, and the test-enforced BR-50 and BR-51; check that every constraint name is 63 characters or fewer.
5. [x] **Database Migration Script** — create `database/migrations/versions/0020_probable_duplicates.py` (revision `0020`, down-revision `0019`): add the new enum value inside `autocommit_block()` (note 2); create the six new tables from `Base.metadata` (the established technique from 0004, 0013, and 0019, which also creates their enum types); then add `ingestion_run_files.duplicate_comparison_id` with its foreign key and index, and the two `CHECK`s, with `op.add_column` / `op.create_foreign_key` / `op.create_index` / `op.create_check_constraint`. Purely additive: no existing column, row, or constraint is changed, and every existing run file keeps its outcome and gets a null link. `downgrade()` reverses in dependency order (checks, index, foreign key, column, then the tables, then the new enum types) and states that the added `ingestionrunfileoutcome` value stays, as in 0005, since PostgreSQL cannot drop an enum value; downgrade therefore requires no run file to be using it, which the migration checks and refuses otherwise with a clear message. **Also modify `0001_initial_schema.py`** (note 3).
6. [x] **Business Logic Unit Testing** — modify `database/tests/test_models.py` (example-based, same convention as the rest of the file):
   - `TestIngestionRunFileProbableDuplicate` (BR-49): a skipped-probable-duplicate row with a comparison and no statement is valid; without a comparison is rejected; any other outcome with a comparison is rejected; with a statement is rejected; existing outcomes unaffected; a comparison with a referencing run file cannot be deleted.
   - `TestKnownFile` (BR-39, BR-40): a valid row for each state; a duplicate hash is rejected; a matched hash equal to its own is rejected; a missing matched hash or comparison is rejected; `state` accepts only the three values; a comparison referenced by a known file cannot be deleted.
   - `TestDuplicateComparison` (BR-42): a valid row; a negative count is rejected; `matched_count` above the smaller count is rejected (and equal to it is valid); a ratio of 1 and of 0 are valid, above 1 and below 0 rejected.
   - `TestDuplicateComparisonRow` (BR-42): a valid out-flow row and in-flow row; both flows, neither flow, and a non-positive flow are rejected; ranks 1 and 10 are valid, 0 and 11 rejected; the same rank twice on one side is rejected, and the same rank on the other side is valid; deleting a comparison deletes its rows; a side with 10 rows is valid.
   - `TestDuplicatePair` (BR-43): a valid pair; hashes in the wrong order and equal hashes are rejected; the same pair twice is rejected; a `keep_hash` that is neither member is rejected; a missing comparison is rejected; the default status is `pending`; the status accepts only the four values.
   - `TestStatementRemovalJob` (BR-45, BR-46): defaults (`queued`, counts 0); two active jobs for one pair are rejected, for each pair of active statuses; a `failed` or `embeddings_failed` job beside an active one is allowed (retry); `embeddings_pending` / `embeddings_failed` without transaction ids are rejected and with them are valid; `failed` / `embeddings_failed` without a reason are rejected; negative counts are rejected; the id list and counts round-trip; a pair with a job cannot be deleted.
   - `TestDuplicateScanState` (BR-48): a row with id 1 and all-null fields is valid; id 2 is rejected; a second row with id 1 is rejected.
   - `TestEpic14ReferencesByHash` (BR-50, BR-51; metadata-only, needs no database): none of the six new tables has a foreign key to `bank_statements`, `statement_accounts`, or `transactions`; and the **set of tables with a foreign-key path (including transitive) to those three equals exactly** `recurring_payment_matches`, `categorization_disagreements`, `recategorization_proposals`, `recategorization_jobs`, and `ingestion_run_files`, so the test fails, with a message naming the new table and the three places to update, when a future feature adds a dependent.
8. [x] **Live verification** (not deferred to Build and Test; using the scratch virtualenv outside the repository as for Epic 13):
   - run the **full** Database test suite against a real disposable PostgreSQL (testcontainers): the existing tests plus the new ones, all passing;
   - `alembic upgrade head` on an **empty** disposable database (the 0001 fix, note 3), then inspect the tables, constraints, indexes, and the enum values directly; `alembic check` to confirm the migrated schema has no drift from the models;
   - **data-preservation check**: on a fresh database upgraded only to `0019`, insert a representative statement, transaction, and run files with each existing outcome; upgrade to `0020`; confirm every row is intact with a null comparison link and that a `skipped_probable_duplicate` row can now be inserted (this is what proves the enum-value commit, note 2); then `alembic downgrade` removes the new objects and leaves those rows intact;
   - on the migrated database confirm the key constraints with raw SQL: the active-job partial unique index, the single-row scan state, the hash ordering with a value that would sort differently under a non-C collation, the comparison-row bound, and a cascade delete;
   - confirm `to_jsonb` / `jsonb_populate_recordset` round-trips a `statement_removal_jobs` row with its array and JSON columns (the Backfill Tool's backup mechanism);
   - confirm running `alembic upgrade head` twice in a row is a safe no-op (the auto-migrate-on-startup contract both backend services rely on);
   - run `ruff` on the unit with its existing configuration;
   - as a regression check only (no edits to those units): re-run the Ingestion Worker and API Service existing test suites, if their environments are available, to confirm the added enum value and column break nothing.
9. [x] **Documentation Generation**: modify `aidlc-docs/construction/database/code/models-summary.md` (an Epic 14 section: rows for the six entities, the `IngestionRunFile` change, migration 0020 and its verification results, and the "contract for Units 2 and 3" below), and check `aidlc-docs/construction/database/code/README.md` for any migration or entity list needing the same update.
10. [x] **Deployment Artifacts**: N/A (no container, port, or compose change; the migration runs through each backend service's existing auto-migrate-on-startup path, to be exercised for real at Build and Test).
11. [x] **Progress**: mark each step above `[x]` as it completes, mark stories US-14.1 to 14.7 `[x]` for their schema layer in the summary's story-coverage note, update `aidlc-state.md`, and confirm via `git status` that only intended files changed and no duplicates were created.

## Story coverage (schema layer)

| Story | What this unit provides |
|---|---|
| US-14.1 | `IngestionRunFile` outcome and comparison link (BR-49); `DuplicateComparison.reason` |
| US-14.2 | `DuplicateComparison` and `DuplicateComparisonRow`, bounded and write-once (BR-42) |
| US-14.3 | `KnownFile.state = overridden` and `decided_at` (BR-41) |
| US-14.4 | `KnownFile`, unique by hash (BR-39), with its evidence (BR-40) |
| US-14.5 | `DuplicatePair` (BR-43, BR-44), `DuplicateScanState` (BR-48) |
| US-14.6 | `StatementRemovalJob` (BR-45, BR-46, BR-47) |
| US-14.7 | Hash-only references and the surviving tables (BR-50); the dependents guard (BR-51); pre-registration shape (BR-40) |

## Contract for Units 2 and 3 (rules this unit deliberately does not enforce; goes into `models-summary.md`)

| Rule | Owner |
|---|---|
| BR-41 remembered-file changes are one-way (insert as `probable_duplicate` or `confirmed_duplicate`; only change is to `overridden`) | Unit 2 (override), Unit 3 (the other writers) |
| BR-44 decided or superseded pairs are never reopened; the scan's insert / refresh / supersede rules; overridden files excluded | Unit 3, Probable Duplicate Detector |
| BR-46 ordering: the deletion and the move to `embeddings_pending` in one transaction | Unit 3, Statement Removal Handler |
| BR-47 removal jobs are never deleted | Units 2 and 3 |
| BR-51 the one list of dependents is used by the removal helper, the backfill wipe, and the API's removal preview | Units 2 and 3 (guard test in this unit) |
| BR-52 a probable-duplicate skip counts as skipped, never as a failure | Unit 3, Ingestion Orchestrator |
| Comparison write-once, and the stored keep-proposal never recomputed by the API | Units 2 and 3 |
| Consumers of the outcome value: `frontend/src/api/types.ts` has `RunFileOutcome` as a closed union and needs the new value | Unit 4 (Frontend), noted here so it is not missed |

## Completion criteria for this unit
- All steps above marked `[x]`.
- Full Database test suite passing against a real PostgreSQL, including every new test.
- Migration 0020 verified live: empty-database upgrade, `alembic check` clean, data preservation across the enum-value change, downgrade, and idempotent re-upgrade.
- No existing file duplicated; no change outside `database/` and `aidlc-docs/`.

## Completion notes (2026-10-03)

All 11 steps done. Results are in `aidlc-docs/construction/database/code/models-summary.md` (Epic 14 section). In short: 185 Database tests pass (89 new); migration 0020 passed 78 live checks; the Ingestion Worker (467) and API Service (261) suites pass unchanged with the changed shared package; `ruff check src tests` is clean.

Differences from the plan as written, all found by running things:
1. **Note 2's fallback (`outcome::text`) was not needed.** `autocommit_block()` works under this project's `env.py`, including in the middle of a run that goes 0018 to 0020.
2. **Step 8's data-preservation check had to simulate an existing database.** A database built from empty already has the new enum value (0001 builds from the current models), so it would never exercise the committed `ADD VALUE`. The verification rebuilds the outcome enum with its original three values first.
3. **`alembic check` is not drift-free, and was not before this work.** It reports exactly the three older raw-SQL partial indexes (BR-10, BR-14, BR-21). The verification asserts that exact set, so any new drift fails it.
4. **One more test than planned**: the collation mutation survived because the test container's default collation is already byte order, so a test now reads the stored constraint definition and requires `COLLATE "C"`.
5. **Python-side defaults**: raw SQL inserts must supply `status`, counts and so on, as for every earlier table; recorded in the contract.
6. Constraint-name length (63 characters) was checked; the longest is 59.

## REOPENED (2026-10-04) — one new column on `duplicate_pairs` — amended steps (approved under the user's standing instruction of 2026-10-04; done)

This plan's Steps 1 to 11 were completed and approved on 2026-10-04. The Ingestion Worker's Functional Design Question 1 = C (a pair of clearly different sizes is listed for information only, with no remove action) needs the worker's decision to be **stored**, because the API Service must not recompute it (Application Design rule, the same one that stores `keep_hash`). That is one new column, so the Database unit is reopened for a small rework. Migration 0020 has not reached any database but disposable test ones (the live database is at 0018 and nothing is committed), so it is **reworked in place**, as 0019 was, rather than followed by a 0021.

**Design source**: the amended Database Functional Design (`domain-entities.md`: `DuplicatePair.removal_allowed`; `business-rules.md`: BR-53; `business-logic-model.md`: pair lifecycle notes).

R1. [x] **Models** — modify `database/src/transactagent_db/models.py`: add `DuplicatePair.removal_allowed` (boolean, **not null, no default**, so a writer must decide it); update the class docstring (BR-53, and that `removed` now means the deletion committed).
R2. [x] **Migration** — edit `0020_probable_duplicates.py` in place: no new statement is needed (the table is created from `Base.metadata`), but update its docstring to say so. Nothing else changes; `0001_initial_schema.py` is unaffected (the table is created only by 0020).
R3. [x] **Tests** — modify `database/tests/test_models.py`: the pair helper supplies `removal_allowed`; new `TestDuplicatePair` cases: both values are storable and round-trip; a missing value is rejected (not null); the existing pair, removal-job, and scan tests keep passing.
R4. [x] **Live verification** — update `verify_migration_0020.py` (the raw-SQL pair inserts supply `removal_allowed`; check the column is `boolean`, `NOT NULL`, no default) and re-run it in full (all 78 checks plus the new one), the full Database suite, `ruff check src tests`, and the Ingestion Worker and API Service regression suites.
R5. [x] **Documentation** — update `aidlc-docs/construction/database/code/models-summary.md` (the `DuplicatePair` row, the test and verification counts, the contract row for BR-53).
R6. [x] **Progress** — mark R1 to R5 `[x]`, update `aidlc-state.md`, and confirm via `git status` that only intended files changed.
