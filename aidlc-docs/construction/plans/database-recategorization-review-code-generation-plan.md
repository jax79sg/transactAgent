# Code Generation Plan — Database Unit — Recategorization Review Panel

**Unit**: Database (Unit 1). **Stories**: US-6.1–US-6.6 (schema layer only — business logic lives in Units 2/3).
**Dependencies**: None (first unit in the package sequence).
**Database entities owned by this unit**: `RecategorizationProposal` (new), plus new relationship edges on `RecategorizationJob`, `Transaction`, `Category`.

Executed directly alongside this plan rather than as a separate prior gate — the change is small, single-table, and closely modeled on the existing `IngestionRunFile`/`RecategorizationJob` patterns (per the approved Functional Design), so plan and generation are presented together for one review, consistent with how this feature's other stages have run. Logged explicitly in `audit.md`.

## Steps

1. [x] **Business Logic Generation** — N/A for this unit (Database owns schema/constraints only; business logic lives in Units 2/3 per Application Design).
2. [x] **Repository Layer Generation** — N/A (this unit has no repository layer of its own; Units 2/3 each own their own data access code against this schema, per `component-dependency.md`).
3. [x] **Database Migration Scripts**:
   - Modified: `database/src/transactagent_db/models.py` — added `RecategorizationProposalSourceBucket`, `RecategorizationProposalStatus` enums; added `RecategorizationProposal` model; added relationship edges on `RecategorizationJob.proposals`, `Transaction.recategorization_proposals`, `Category.proposed_in_recategorization_proposals`
   - Created: `database/migrations/versions/0004_recategorization_proposals.py`
4. [x] **Business Logic Unit Testing**:
   - Modified: `database/tests/test_models.py` — added `TestRecategorizationProposal` (4 tests)
5. [x] **Documentation Generation**:
   - Modified: `aidlc-docs/construction/database/code/models-summary.md`

## Verification (not deferred to Build & Test — done now, live)

- [x] Ran the full `database` unit test suite against a real disposable Postgres (testcontainers): 16/16 passing
- [x] Ran `alembic upgrade head` against a separate real disposable Postgres container — caught and fixed a real bug (two enum columns in one hand-written `op.create_table()` call double-fires `CREATE TYPE`, per a known SQLAlchemy/Alembic issue) by switching to the `Base.metadata`-driven table creation technique `0001_initial_schema.py` already established, rather than hand-duplicating column definitions
- [x] Verified the table shape and the BR-14 partial unique index directly via `psql \d`/`\di`
- [x] Verified `alembic downgrade` cleanly drops the table and both enum types
- [x] Verified running `alembic upgrade head` twice in a row is a safe no-op (matches the auto-migrate-on-startup contract both backend units rely on)
