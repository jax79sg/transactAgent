# Domain Entities — Unit 1: Database

Technology-agnostic domain model. Exact column types/engine choice (PostgreSQL, etc.) are confirmed in NFR Requirements; types below are logical (e.g., "decimal(18,2)" describes precision intent, not a specific SQL dialect).

## Entity: User
- `id` (PK)
- `username` (unique)
- `password_hash`
- `created_at`

**Purpose**: Single-user login credential (FR-9.1/9.2, US-5.1).

## Entity: Category
- `id` (PK)
- `name` (unique across all rows, active or inactive)
- `active` (boolean, default true) — soft-delete flag (Question 3 = B)
- `is_reserved` (boolean, default false) — true only for the system-seeded `UNSURE` row; prevents deletion/rename
- `created_at`
- `updated_at`

**Purpose**: The 46-entry whitelist (45 user categories + `UNSURE`) from requirements.md Section 5. Seeded at first migration.

## Entity: BankStatement
- `id` (PK)
- `drive_file_id`
- `pdf_content_hash` (unique) — FR-3.1
- `bank_name` (nullable until extraction determines it)
- `processed_at`

**Purpose**: One row per successfully-processed statement PDF; the record duplicate detection checks against (FR-3.2/3.3).

## Entity: Transaction
- `id` (PK)
- `bank_statement_id` (FK -> BankStatement)
- `transaction_date`
- `description`
- `out_flow` (decimal(18,2), nullable)
- `in_flow` (decimal(18,2), nullable)
- `currency` (original currency code, e.g., "USD")
- `bank_name`
- `category_id` (FK -> Category)
- `category_source` (enum: `similarity` | `llm` | `manual` | `unsure`)
- `converted_amount_sgd` (decimal(18,2), nullable) — Question 1 = A, stored
- `conversion_is_approximate` (boolean, default false)
- `conversion_unavailable` (boolean, default false)
- `fx_rate_used_id` (FK -> FxRateCache, nullable)
- `created_at`
- `updated_at`

**Purpose**: The core transaction record (FR-4.1). Both original and converted amounts retained (FR-10.2).

## Entity: FxRateCache
- `id` (PK)
- `from_currency`
- `to_currency` (always `SGD` per FR-10.1, but modeled generically)
- `rate_date` (the date this rate applies to)
- `rate` (decimal)
- `fetched_at`

**Purpose**: Cached historical FX rates (FR-10.3/10.4), keyed by currency pair + date.

## Entity: IngestionRun
- `id` (PK)
- `status` (enum: `queued` | `running` | `completed` | `completed_with_failures` | `failed`)
- `triggered_by_user_id` (FK -> User)
- `started_at`
- `completed_at` (nullable)
- `files_found_count`
- `files_processed_count`
- `files_skipped_count`
- `files_failed_count`

**Purpose**: One row per manually-triggered ingestion run (FR-1.4, US-1.2/1.5).

## Entity: IngestionRunFile
- `id` (PK)
- `ingestion_run_id` (FK -> IngestionRun)
- `drive_file_id`
- `drive_file_name`
- `outcome` (enum: `processed` | `skipped_duplicate` | `failed`)
- `failure_reason` (nullable string)
- `raw_extracted_text` (nullable, large text) — Question 2 = B
- `bank_statement_id` (FK -> BankStatement, nullable — set when outcome = `processed`)
- `transactions_extracted_count` (nullable int)
- `processed_at`

**Purpose**: Per-file outcome within a run, supporting the US-1.5 drill-down and OCR/parse failure debugging (Question 2 = B retains raw text for troubleshooting).

## Entity: RecategorizationJob
- `id` (PK)
- `status` (enum: `queued` | `running` | `completed` | `failed`)
- `source_transaction_id` (FK -> Transaction) — the manually-corrected transaction that triggered this job
- `created_at`
- `completed_at` (nullable)
- `updated_transaction_count` (nullable int)

**Purpose**: The FR-5.4 retroactive-recategorization job queue record, dispatched from the API Service (Unit 2) to the Ingestion Worker Service (Unit 3) via this shared table (per Application Design `services.md`).

---

## Entity: RecategorizationProposal (added 2026-08-02 — Recategorization Review Panel, Epic 6)
- `id` (PK)
- `recategorization_job_id` (FK -> RecategorizationJob) — the correction event that generated this proposal
- `candidate_transaction_id` (FK -> Transaction) — the transaction this proposal would change
- `proposed_category_id` (FK -> Category)
- `match_score` (decimal) — the similarity score behind this proposal
- `source_bucket` (enum: `unsure` | `categorized`) — which search bucket the candidate came from (FR-RR-1)
- `status` (enum: `pending` | `approved` | `rejected` | `auto_applied`)
- `created_at`
- `resolved_at` (nullable) — set when status leaves `pending`

**Purpose**: Records every candidate match found by the broadened recategorization search (FR-RR-1/2), whether it was auto-applied (FR-RR-3) or is awaiting human review (FR-RR-4/US-6.4). `status = auto_applied` rows are a record of what happened automatically, not an action item — the Recategorization Review Component's pending list (US-6.4) and count (US-6.6) only ever query `status = 'pending'`.

## Entity: BackupRun (added 2026-08-08 — Nightly Transaction Backup, Epic 7)
- `id` (PK)
- `backup_date` (date, unique) — the calendar day this attempt belongs to
- `started_at`
- `completed_at`
- `outcome` (enum: `success` | `failed`)
- `failure_category` (enum: `drive_connectivity` | `other`, nullable) — set only when `outcome = 'failed'`
- `transaction_count` (nullable int) — number of transactions included in the CSV snapshot; set only on success
- `backup_filename` (nullable string) — the uploaded file's name in the `backup` Drive subfolder; set only on success

**Purpose**: One row per nightly backup attempt (FR-1..FR-11, Epic 7), written once at completion by the Ingestion Worker's Backup Manager, read read-only by the API Service's Backup Status Component. Unlike `IngestionRun`/`RecategorizationJob`, this entity has no `queued`/`running` interim status — see `business-logic-model.md` for why. Standalone entity: it does not reference individual `Transaction` rows (it's a per-attempt summary, not a per-item audit trail like `IngestionRunFile`).

## Entity: OAuthCredential (added 2026-08-01, retroactively — see audit.md)
- `id` (PK)
- `provider` (unique, e.g. `google_drive`)
- `refresh_token`
- `access_token` (nullable)
- `access_token_expires_at` (nullable)
- `connected_at`
- `updated_at`

**Purpose**: Stores the refresh token from the one-time interactive Google OAuth consent (US-1.1). Added during Unit 3's NFR Requirements after Functional Design left the OAuth mechanism underspecified — Unit 3 has no browser-facing interface, so Unit 2 handles the interactive handshake (`/drive/connect`, `/drive/callback`) and writes the result here for Unit 3's Drive Connector to read.

## Entity Relationship Diagram (text)

```
User (1) ----< IngestionRun (1) ----< IngestionRunFile (1) ---- (0..1) BankStatement (1) ----< Transaction
                                                                                                    |
Category (1) ----< Transaction                                                                     |
                                                                                                    |
FxRateCache (1) ----< Transaction (via fx_rate_used_id)                                            |
                                                                                                    |
Transaction (1) ----< RecategorizationJob (via source_transaction_id)
RecategorizationJob (1) ----< RecategorizationProposal (via recategorization_job_id)
Transaction (1) ----< RecategorizationProposal (via candidate_transaction_id)
Category (1) ----< RecategorizationProposal (via proposed_category_id)
```

**Cardinality notes**:
- One `IngestionRun` has many `IngestionRunFile` rows (one per PDF scanned)
- One `IngestionRunFile` links to zero or one `BankStatement` (zero if skipped/failed)
- One `BankStatement` has many `Transaction` rows
- One `Category` has many `Transaction` rows
- One `FxRateCache` row may be referenced by many `Transaction` rows (same-date same-pair reuse, FR-10.4)
- One `Transaction` may be the source of many `RecategorizationJob` rows over time (re-corrected more than once)
- One `RecategorizationJob` has zero or more `RecategorizationProposal` rows — zero if the broadened search (FR-RR-1) finds no candidates at all
- One `Transaction` may be the *candidate* of many `RecategorizationProposal` rows over time (proposed against on separate correction events — no suppression memory, per FR-RR-8/US-6.5); it is never both source and candidate of the same proposal (self-match exclusion, US-6.1)
