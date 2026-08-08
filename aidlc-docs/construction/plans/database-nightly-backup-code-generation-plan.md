# Code Generation Plan — Database Unit — Nightly Transaction Backup

**Unit**: Database (Unit 1). **Stories**: US-7.1–US-7.4 (schema layer only — business logic lives in Unit 3, status exposure in Unit 2).
**Dependencies**: None (first unit in this feature's build sequence, per the approved execution plan).
**Database entities owned by this unit**: `BackupRun` (new, standalone — no new relationship edges on existing entities).

Executed directly alongside this plan rather than as a separate prior gate — the change is small, single-table, write-once (per Functional Design), and closely modeled on the existing `RecategorizationProposal` migration pattern. Plan and generation presented together for one review, consistent with how this project's other units have run.

## Steps

1. [x] **Business Logic Generation** — N/A for this unit (Database owns schema/constraints only; business logic lives in Unit 3's Backup Manager, status exposure in Unit 2's Backup Status Component, per Application Design).
2. [x] **Repository Layer Generation** — N/A (this unit has no repository layer of its own; Units 2/3 each own their own data access code against this schema).
3. [x] **Database Migration Scripts**:
   - Modify: `database/src/transactagent_db/models.py` — add `BackupRunOutcome`, `BackupRunFailureCategory` enums; add `BackupRun` model (BR-17 unique `backup_date`, BR-18 CHECK constraint)
   - Create: `database/migrations/versions/0006_backup_runs.py`
4. [x] **Business Logic Unit Testing**:
   - Modify: `database/tests/test_models.py` — add `TestBackupRun`
5. [x] **Documentation Generation**:
   - Modify: `aidlc-docs/construction/database/code/models-summary.md`

## Verification (not deferred to Build & Test — done now, live)

- [x] Run the full `database` unit test suite against a real disposable Postgres (testcontainers): 24/24 passing
- [x] Run `alembic upgrade head` against a separate real disposable Postgres container (docker run postgres:16-alpine) — this table has two enum columns (`outcome`, `failure_category`), so it reuses the `Base.metadata`-driven table creation technique (not hand-written `op.create_table()` with inline `sa.Enum()`) that `0004_recategorization_proposals.py` already established, to avoid the known double-`CREATE TYPE` SQLAlchemy/Alembic bug documented there. **Found a pre-existing, out-of-scope bug while doing this**: migration 0005 (`ingestion_run_cancellation`, already in the repo before this feature) fails against a genuinely fresh database with `DuplicateColumn: column "cancel_requested_at" of relation "ingestion_runs" already exists`. Root cause: 0001's table-name scoping (`_INITIAL_TABLE_NAMES`) protects against re-creating whole tables added by later migrations, but NOT against columns added to an *already-scoped* table — `IngestionRun.cancel_requested_at` is a real column on the model today, so 0001's `Base.metadata.create_all()` already creates `ingestion_runs` with that column, and 0005's `ALTER TABLE ADD COLUMN` then collides. This does not affect the live project database (already upgraded past 0005 with the column already present) and is unrelated to this feature's `backup_runs` table — flagged to the user rather than silently fixed, since it's outside this feature's scope. Worked around for verification purposes only: built schema via `Base.metadata.create_all()` (all tables except `backup_runs`) + `alembic stamp 0005`, then ran `alembic upgrade head` to apply 0006 in isolation.
- [x] Verified the table shape and BR-17/BR-18 constraints directly via `psql \d backup_runs` — both the unique constraint and the CHECK constraint are present exactly as designed
- [x] Verified `alembic downgrade 0005` cleanly drops the table and both enum types (`\dt`/`\dT` empty after)
- [x] Verified running `alembic upgrade head` twice in a row is a safe no-op (second run produced no output/changes)
