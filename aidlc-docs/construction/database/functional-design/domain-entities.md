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
- `embedding_status` (enum: `pending` | `completed`, default `pending`) — *added 2026-08-11, Local Embedding-Based Semantic Similarity, Epic 9*
- `llm_suggested_category_id` (FK -> Category, nullable) — *added 2026-08-16, Matching Precision Refinement*

**Purpose**: The core transaction record (FR-4.1). Both original and converted amounts retained (FR-10.2).
**Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)**: `embedding_status` tracks whether this transaction's own embedding has been computed and persisted to the Vector DB (FR-6/FR-7) — the field the API Service's badge reflects (US-9.1). Defaulting new rows to `pending` is also how the one-time historical backfill (FR-11) works: no separate backfill flag or table is needed — every pre-existing transaction just starts out `pending` too (via the migration's default), and the Ingestion Worker's Embedding Manager Component drains the `pending` backlog the same way regardless of whether a row is old or new (BR-24). No embedding vector itself is stored here — only this status; the vector lives in the separate Vector DB, keyed by this row's `id`.
**Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: `llm_suggested_category_id` records what the always-on LLM classification step (FR-MPR-1) decided for this transaction at ingestion time — `null` when the LLM abstained (returned `UNSURE`) or its endpoint was unreachable, never a sentinel row. Written once, by the Ingestion Worker's Categorization Engine, at the same time the transaction itself is first persisted (BR-26) — never updated afterward, even if the transaction's actual `category_id` later changes via manual correction or proposal approval. Its sole purpose is letting the retroactive re-scan (`recategorizeUnsureFromPrecedent`) read back a candidate transaction's own original LLM opinion as a score-boost signal (FR-MPR-7), without re-calling the LLM for transactions ingested in an earlier run. Distinct from `category_id` (the transaction's actual, currently-assigned category) — this field is read-only historical signal, never itself shown to the user or treated as an assignment.

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

## Entity: CategorizationDisagreement (added 2026-08-16 — Matching Precision Refinement)
- `id` (PK)
- `transaction_id` (FK -> Transaction) — the transaction left `UNSURE` pending this decision
- `similarity_category_id` (FK -> Category) — the category found by embedding/fuzzy similarity matching
- `llm_category_id` (FK -> Category) — the category found by the always-on LLM classification
- `similarity_score` (decimal) — the similarity match's score, same scale/meaning as `RecategorizationProposal.match_score`
- `status` (enum: `pending` | `resolved` | `rejected`)
- `resolved_category_id` (FK -> Category, nullable) — set only when `status = resolved`; equals either `similarity_category_id` or `llm_category_id`, never a third value (BR-27)
- `created_at`
- `resolved_at` (nullable) — set when status leaves `pending`

**Purpose**: Records a genuine categorization disagreement (FR-MPR-6's third bullet: both similarity matching and the always-on LLM produce a category, and they differ, FR-MPR-9) — a case today's schema has no room for, since `RecategorizationProposal` assumes exactly one proposed category and a triggering `RecategorizationJob`, neither of which exists here (there is no manual correction that triggered this; it arises directly during ingestion-time `categorize()`). Deliberately a standalone entity rather than an extension of `RecategorizationProposal` — see the Application Design plan doc's "Key Design Resolution 1" for the full reasoning. Written by the Ingestion Worker's Categorization Engine; read and resolved by the API Service's Recategorization Review Component (extended, not duplicated) via pick-one-or-reject, surfaced on the existing Review page alongside (but visually distinct from) the existing `ProposalTable` rows.

## Entity: SettingChange (added 2026-08-16 — Configurable Application Settings)
- `id` (PK)
- `setting_name` (string) — e.g. `similarity_threshold`; not a DB-level enum/FK, see BR-29
- `owning_service` (enum: `ingestion-worker` | `api-service`)
- `previous_value` (string, nullable) — null only for a setting's first-ever recorded change (i.e. changed from its built-in default, which was never itself a `SettingChange` row)
- `new_value` (string)
- `changed_at` (timestamp)

**Purpose**: An append-only audit log of every successful `updateSetting()` call (FR-CAS-9, US-10.4), read by the Configuration Component's `listSettingHistory()`. Values are stored as strings regardless of the setting's real type (float/int/str/enum) — a single, uniform column shape for 40 heterogeneous settings (corrected from an original miscount of 35 -- see requirements.md's Post-Approval Change section), matching the pattern this project already uses for `RecategorizationProposal.match_score`-style typed-but-simple columns rather than a polymorphic value-type scheme. Type/range validation happens at the application layer (Configuration Component, against the allow-list's metadata) *before* a row is ever written — `SettingChange` itself carries no validation logic, only a record of what happened. No relationship to any other entity — self-contained, unlike every other new entity added by a prior feature (see Entity Relationship Diagram below).

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

## Entity: RecurringPayment (added 2026-08-08 — Recurring Payments, Epic 8)
- `id` (PK)
- `name` (string)
- `expected_amount` (decimal(18,2)) — a loose guide, not an exact-match requirement (FR-5)
- `frequency` (enum: `monthly` | `annual`)
- `due_month` (int 1–12, nullable) — set only when `frequency = 'annual'` (BR-19)
- `due_day` (int 1–31)
- `category_id` (FK -> Category, nullable) — optional link (FR-1/US-8.1)
- `is_trusted` (boolean, default false) — one-way false→true, set on first approved match (FR-7)
- `created_at`, `updated_at`
- `embedding_status` (enum: `pending` | `completed`, default `pending`) — *added 2026-08-12, retroactively during Ingestion Worker Service Functional Design, Local Embedding-Based Semantic Similarity, Epic 9 — see `ingestion-worker-embedding-similarity-functional-design-plan.md` and audit.md*

**Purpose**: The user-maintained register of expected recurring payments (FR-1..3). `is_trusted` is what gates FR-7's tolerance-based auto-apply — see `business-logic-model.md`.

**Addendum (2026-08-12, Local Embedding-Based Semantic Similarity feature — Epic 9, added retroactively)**: `embedding_status` mirrors `Transaction.embedding_status` (BR-24) — it's what the Ingestion Worker's Embedding Manager Component drains to populate the vector store's `recurring_payment_names` collection, which `matchNewTransaction`/`runDetectionScan` query. Unlike `Transaction` (immutable description once persisted), `RecurringPayment.name` can be edited via the API Service's register CRUD (FR-1) — see BR-25 for why writes to this field are split across both services, not just the Worker.

## Entity: RecurringPaymentMatch (added 2026-08-08 — Epic 8)
- `id` (PK)
- `recurring_payment_id` (FK -> RecurringPayment)
- `transaction_id` (FK -> Transaction)
- `cycle_period` (string, e.g. `"2026-08"` for a monthly payment or `"2026"` for an annual one) — identifies which due cycle this match covers
- `status` (enum: `pending` | `approved` | `rejected` | `auto_applied`)
- `amount_at_match` (decimal(18,2)) — snapshot of the matched transaction's amount at match time
- `created_at`
- `resolved_at` (nullable) — set when status leaves `pending`

**Purpose**: One row per candidate match found by the Recurring Payment Manager (FR-5), structurally the closest sibling to `RecategorizationProposal` in this schema — a `pending` review record that resolves to `approved`/`rejected` via user action, or is created directly as `auto_applied` for a trusted payment within tolerance (FR-7). `cycle_period` plays the role `recategorization_job_id` plays there: the thing BR-21's uniqueness rule groups by.

## Entity: DetectionSuggestion (added 2026-08-08 — Epic 8)
- `id` (PK)
- `description_pattern` (string, unique — BR-22) — a normalized/representative description identifying this recurring charge pattern
- `suggested_amount` (decimal(18,2))
- `suggested_category_id` (FK -> Category, nullable)
- `occurrence_count` (int) — how many historical transactions matched this pattern when detected
- `status` (enum: `new` | `dismissed` | `added`)
- `created_at`
- `resolved_at` (nullable)

**Purpose**: Untracked recurring-charge suggestions from the Recurring Payment Manager's periodic detection scan (FR-12). The unique constraint on `description_pattern` is the entire mechanism behind FR-13's "a dismissed suggestion never reappears" — a re-scan finds the existing row and skips creating a duplicate, rather than the Worker needing to remember dismissals separately.

## Entity: DetectionScanRun (added 2026-08-08, retroactively during Ingestion Worker Code Generation — see audit.md)
- `id` (PK)
- `ran_at`

**Purpose**: One row per completed detection scan attempt (WR-19) — the entity backing `isDetectionScanDueNow()`'s due-check, mirroring `BackupRun`'s write-once shape (a scan is synchronous within one poll cycle, not a cross-service handoff). No failure-classification fields — unlike a backup attempt, a failed scan simply leaves no row, remaining due on the next poll cycle, which is harmless since scans are read-only until they insert `DetectionSuggestion` rows. Added after Application/Functional Design's `isDetectionScanDueNow()` pseudocode assumed this shape existed without the backing entity having been specified.

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

Category (1) ----< RecurringPayment (via category_id, optional)
RecurringPayment (1) ----< RecurringPaymentMatch (via recurring_payment_id)
Transaction (1) ----< RecurringPaymentMatch (via transaction_id)
Category (1) ----< DetectionSuggestion (via suggested_category_id, optional)
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
- One `RecurringPayment` has many `RecurringPaymentMatch` rows over time (one per cycle it was ever matched against), but at most one *live* (non-rejected) match per `cycle_period` (BR-21)
- One `Transaction` is matched to at most one `RecurringPaymentMatch` in practice (a transaction is one real-world payment), though the schema doesn't need to forbid more than one — that would only happen if the same transaction genuinely satisfied two different recurring payments' matching criteria, an edge case left to application-layer matching logic (Ingestion Worker) rather than a DB constraint
- `SettingChange` (added 2026-08-16) is deliberately absent from the diagram above, same as `BackupRun` — a standalone, FK-less audit log with no relationship to any other entity
