# Code Generation Plan — Database Unit: Local Embedding-Based Semantic Similarity

## Unit Context
- **Unit**: Database. Single new field on the existing `Transaction` entity (BR-24) — no new table.
- **Traces to**: `embedding-similarity-requirements.md` FR-6/FR-7/FR-11; `business-rules.md` BR-24
- **Dependencies**: None new (pure SQLAlchemy/Alembic, same as every prior migration)
- **Files touched**: `database/src/transactagent_db/models.py` (modify), `database/migrations/versions/0009_transaction_embedding_status.py` (new), `database/tests/test_models.py` (extend)

## Steps

### Step 1: Business Logic Generation
- [x] Add `EmbeddingStatus` enum (`pending`|`completed`) to `models.py`.
- [x] Add `Transaction.embedding_status` column (`_enum_type(EmbeddingStatus)`, `nullable=False`,
  `server_default=EmbeddingStatus.PENDING.value`) — BR-24.

### Step 2: Database Migration Scripts
- [x] Create migration `0009_transaction_embedding_status.py`: explicitly `.create()`s the
  `embeddingstatus` Postgres enum type, then `op.add_column` on `transactions` with
  `server_default='pending'` — this single default is what backfills every pre-existing row (FR-11)
  without a separate UPDATE script. `downgrade()` drops the column then the enum type.

### Step 3: Business Logic Unit Testing
- [x] Add `TestTransactionEmbeddingStatus` to `test_models.py`: default-value test, transition-to-completed
  test.

### Step 4: Business Logic Summary
- [x] Update `models-summary.md` with the new field, enum, and migration-verification notes.

## Live Verification (not just unit tests)
- [x] Rebuilt + redeployed `ingestion-worker` (shares the `transactagent_db` package) against the real
  running Postgres — confirmed via `alembic_version` reaching `0009`.
- [x] Confirmed all 6142 pre-existing `transactions` rows backfilled to `pending` by the column default
  alone.
- [x] Verified downgrade (`0009 -> 0008`, column + enum type both cleanly dropped) and idempotent re-upgrade
  (`0008 -> 0009`, re-backfill, no errors).
- [x] Found and fixed one real issue during this live check: `create_type=False` belongs on the
  `postgresql.ENUM(...)` constructor, not as an `sa.Column(...)` kwarg (produced a real `SAWarning`, not
  caught by the unit test suite since it never exercises this migration file — `Base.metadata.create_all()`
  builds the test schema directly).
