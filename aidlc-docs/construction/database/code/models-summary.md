# Domain Models Summary — Unit 1: Database

Implemented in [`database/src/transactagent_db/models.py`](../../../../database/src/transactagent_db/models.py).

| Entity | Table | Key constraints |
|---|---|---|
| `User` | `users` | unique `username` |
| `Category` | `categories` | unique `name` (BR-4); `active` soft-delete flag (BR-6); `is_reserved` marks `UNSURE` (BR-5) |
| `BankStatement` | `bank_statements` | unique `pdf_content_hash` (BR-3) |
| `Transaction` | `transactions` | CHECK: exactly one flow direction (BR-2); CHECK: conversion-flag consistency (BR-8); indexes on date/category/bank/statement; `embedding_status` (BR-24, added 2026-08-11 via migration 0009, Epic 9) — `server_default='pending'`, one-way to `completed`, no `failed` state |
| `FxRateCache` | `fx_rate_cache` | unique `(from_currency, to_currency, rate_date)` (BR-7) |
| `IngestionRun` | `ingestion_runs` | BR-10 (single active run) enforced via raw-SQL partial unique index in the initial migration |
| `IngestionRunFile` | `ingestion_run_files` | CHECK: failed outcome requires a reason (BR-9) |
| `RecategorizationJob` | `recategorization_jobs` | references the manually-corrected source transaction |
| `OAuthCredential` | `oauth_credentials` | unique `provider`; added 2026-08-01 via migration 0002, retroactively during Unit 3 NFR Requirements (see audit.md) |
| `RecategorizationProposal` | `recategorization_proposals` | added 2026-08-02 via migration 0004 (Epic 6, Recategorization Review Panel); BR-14 (one pending proposal per candidate+job) enforced via raw-SQL partial unique index, same pattern as `IngestionRun`'s BR-10 |
| `BackupRun` | `backup_runs` | added 2026-08-08 via migration 0006 (Epic 7, Nightly Transaction Backup); BR-17 (one attempt per calendar day) enforced via a standard unique constraint on `backup_date`; BR-18 (failure_category consistency) enforced via a standing CHECK constraint. Standalone entity, no relationship edges to other tables — write-once, no `queued`/`running` interim status (see `business-logic-model.md`) |
| `RecurringPayment` | `recurring_payments` | added 2026-08-08 via migration 0007 (Epic 8, Recurring Payments); BR-19 (annual requires due_month) and BR-20 (due_day 1-31) enforced via standing CHECK constraints; optional edge to `Category`; `embedding_status` (BR-25, added 2026-08-13 via migration 0010, retroactively during Ingestion Worker Service Functional Design/Code Generation, Epic 9) — `server_default='pending'`, reuses the `embeddingstatus` enum type from migration 0009; unlike `Transaction.embedding_status`, can also be reset `completed` -> `pending` by the API Service on a name-changing update |
| `RecurringPaymentMatch` | `recurring_payment_matches` | added 2026-08-08 via migration 0007; BR-21 (one live match per payment+cycle) enforced via raw-SQL partial unique index, same pattern as `IngestionRun`'s BR-10 and `RecategorizationProposal`'s BR-14 |
| `DetectionSuggestion` | `detection_suggestions` | added 2026-08-08 via migration 0007; BR-22 (`description_pattern` uniqueness) enforced via a standard unique constraint — the entire mechanism behind sticky dismissal (FR-13), no application-layer bookkeeping needed |
| `DetectionScanRun` | `detection_scan_runs` | added 2026-08-08 via migration 0008, retroactively during Ingestion Worker Code Generation — backs `isDetectionScanDueNow()`'s due-check; write-once, no relationship edges, same reasoning as `BackupRun` but without failure-classification fields |

All enums (`CategorySource`, `IngestionRunStatus`, `IngestionRunFileOutcome`, `RecategorizationJobStatus`, `RecategorizationProposalSourceBucket`, `RecategorizationProposalStatus`, `BackupRunOutcome`, `BackupRunFailureCategory`, `RecurringPaymentFrequency`, `RecurringPaymentMatchStatus`, `DetectionSuggestionStatus`, `EmbeddingStatus`) are defined as Python `str, enum.Enum` classes and mapped natively by SQLAlchemy 2.0's declarative type system.

**Migration 0009 verification (2026-08-11, Epic 9)**: live-verified against the real running Postgres via the api-service/ingestion-worker's own advisory-lock startup path (rebuilt + redeployed `ingestion-worker`) — `alembic_version` reached `0009`; all 6142 pre-existing `transactions` rows were backfilled to `embedding_status = 'pending'` by the column's `server_default` alone, no separate UPDATE needed, confirming FR-11's "single default unifies forward + backfill" design. Downgrade (`0009 -> 0008`) cleanly dropped both the column and the `embeddingstatus` Postgres enum type; re-upgrade (`0008 -> 0009`) was verified idempotent, correctly re-backfilling all rows to `pending` with no errors or duplicate-type warnings (one real issue found and fixed during this live check: `create_type=False` needs to be passed to the `postgresql.ENUM(...)` constructor, not as an `sa.Column(...)` kwarg — the latter produced a harmless-looking but real `SAWarning`, caught only by actually running the migration against live Postgres, not by the unit test suite, which builds its schema via `Base.metadata.create_all()` and never exercises this migration file at all).

Business rules not expressible as standing SQL constraints (BR-5's "exactly one reserved row", BR-6's "inactive categories not selectable going forward", BR-11, BR-12) are documented in the model docstrings/comments as application-layer responsibilities for Units 2 and 3.
