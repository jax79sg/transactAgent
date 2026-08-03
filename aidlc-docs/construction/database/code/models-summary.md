# Domain Models Summary — Unit 1: Database

Implemented in [`database/src/transactagent_db/models.py`](../../../../database/src/transactagent_db/models.py).

| Entity | Table | Key constraints |
|---|---|---|
| `User` | `users` | unique `username` |
| `Category` | `categories` | unique `name` (BR-4); `active` soft-delete flag (BR-6); `is_reserved` marks `UNSURE` (BR-5) |
| `BankStatement` | `bank_statements` | unique `pdf_content_hash` (BR-3) |
| `Transaction` | `transactions` | CHECK: exactly one flow direction (BR-2); CHECK: conversion-flag consistency (BR-8); indexes on date/category/bank/statement |
| `FxRateCache` | `fx_rate_cache` | unique `(from_currency, to_currency, rate_date)` (BR-7) |
| `IngestionRun` | `ingestion_runs` | BR-10 (single active run) enforced via raw-SQL partial unique index in the initial migration |
| `IngestionRunFile` | `ingestion_run_files` | CHECK: failed outcome requires a reason (BR-9) |
| `RecategorizationJob` | `recategorization_jobs` | references the manually-corrected source transaction |
| `OAuthCredential` | `oauth_credentials` | unique `provider`; added 2026-08-01 via migration 0002, retroactively during Unit 3 NFR Requirements (see audit.md) |
| `RecategorizationProposal` | `recategorization_proposals` | added 2026-08-02 via migration 0004 (Epic 6, Recategorization Review Panel); BR-14 (one pending proposal per candidate+job) enforced via raw-SQL partial unique index, same pattern as `IngestionRun`'s BR-10 |

All enums (`CategorySource`, `IngestionRunStatus`, `IngestionRunFileOutcome`, `RecategorizationJobStatus`, `RecategorizationProposalSourceBucket`, `RecategorizationProposalStatus`) are defined as Python `str, enum.Enum` classes and mapped natively by SQLAlchemy 2.0's declarative type system.

Business rules not expressible as standing SQL constraints (BR-5's "exactly one reserved row", BR-6's "inactive categories not selectable going forward", BR-11, BR-12) are documented in the model docstrings/comments as application-layer responsibilities for Units 2 and 3.
