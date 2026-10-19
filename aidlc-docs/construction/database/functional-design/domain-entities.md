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
- *(no account or closing-balance columns: a statement may hold several accounts, so those live on `StatementAccount` — revised 2026-10-03, see below)*

**Purpose**: One row per successfully-processed statement PDF; the record duplicate detection checks against (FR-3.2/3.3).

**Addendum (2026-10-02, Account Balance at a Point in Time — Epic 13)**:
- **Revised 2026-10-03 (Scope Change: several accounts per PDF)**: the original design put `account_id`, `closing_balance`, and `closing_balance_date` on this entity, which assumes one account per statement. That assumption was dropped (clarification Q1 = B), so the three columns are **not** added here: they belong to the new `StatementAccount` entity, one row per account the statement holds. Statements ingested before the backfill simply have no `StatementAccount` rows until the backfill re-ingests them. `bank_name` here remains the statement-level display name.
- There is deliberately **no** per-statement account type: only `Account.account_type` exists. Nothing in the requirements or stories reads an as-extracted copy, and the user-correctable value on `Account` is the one that matters.

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
- `statement_account_id` (FK -> StatementAccount, **nullable**) — *added 2026-10-03, Epic 13 Scope Change*

**Purpose**: The core transaction record (FR-4.1). Both original and converted amounts retained (FR-10.2).
**Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)**: `embedding_status` tracks whether this transaction's own embedding has been computed and persisted to the Vector DB (FR-6/FR-7) — the field the API Service's badge reflects (US-9.1). Defaulting new rows to `pending` is also how the one-time historical backfill (FR-11) works: no separate backfill flag or table is needed — every pre-existing transaction just starts out `pending` too (via the migration's default), and the Ingestion Worker's Embedding Manager Component drains the `pending` backlog the same way regardless of whether a row is old or new (BR-24). No embedding vector itself is stored here — only this status; the vector lives in the separate Vector DB, keyed by this row's `id`.
**Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: `llm_suggested_category_id` records what the always-on LLM classification step (FR-MPR-1) decided for this transaction at ingestion time — `null` when the LLM abstained (returned `UNSURE`) or its endpoint was unreachable, never a sentinel row. Written once, by the Ingestion Worker's Categorization Engine, at the same time the transaction itself is first persisted (BR-26) — never updated afterward, even if the transaction's actual `category_id` later changes via manual correction or proposal approval. Its sole purpose is letting the retroactive re-scan (`recategorizeUnsureFromPrecedent`) read back a candidate transaction's own original LLM opinion as a score-boost signal (FR-MPR-7), without re-calling the LLM for transactions ingested in an earlier run. Distinct from `category_id` (the transaction's actual, currently-assigned category) — this field is read-only historical signal, never itself shown to the user or treated as an assignment.

**Addendum (2026-10-03, Account Balance at a Point in Time — Epic 13 Scope Change)**: `statement_account_id` links a transaction to the account section of its statement it was printed under, and so to its account (a transaction has no direct account reference). It is nullable only because transactions ingested before the backfill have no section until the backfill re-ingests them; every transaction ingested afterward always has one (application layer). `bank_statement_id` stays required. The schema guarantees the linked section belongs to the **same statement** as `bank_statement_id` (BR-38).

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
- `outcome` (enum: `processed` | `skipped_duplicate` | `skipped_probable_duplicate` | `failed`) — `skipped_probable_duplicate` added 2026-10-03 (Epic 14)
- `failure_reason` (nullable string)
- `raw_extracted_text` (nullable, large text) — Question 2 = B
- `bank_statement_id` (FK -> BankStatement, nullable — set when outcome = `processed`)
- `transactions_extracted_count` (nullable int)
- `duplicate_comparison_id` (FK -> DuplicateComparison, nullable — added 2026-10-03, Epic 14; set exactly when `outcome = 'skipped_probable_duplicate'`, BR-49)
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

## Entity: Account (added 2026-10-02 — Account Balance at a Point in Time, Epic 13)
- `id` (PK)
- `name` — user-editable display name; never empty. Its initial value is derived by the Ingestion Worker's Account Resolver from the bank name and account identifier (exact derivation: Ingestion Worker Functional Design)
- `bank_name` — the bank name in display form, as first seen on a statement
- `account_type` — enum: `deposit` (savings or current) | `credit_card` | `unknown`; default `unknown` (FR-AB-4, A-1, A-3)
- `type_user_set` (boolean, default false) — true once the user has corrected the type through the Account Management Component; see BR-34
- `currency` (3-letter code) — fixed at creation, BR-31 (A-6)
- `created_at`
- `updated_at`

**Purpose**: A real-world account the user holds, created automatically from statement headers (FR-AB-1/2) and tidied by the user (rename, merge, correct type — FR-AB-3). Only `deposit` accounts take part in balances (FR-AB-4).

## Entity: AccountKey (added 2026-10-02 — Account Balance at a Point in Time, Epic 13)
- `id` (PK)
- `account_id` (FK -> Account, required)
- `bank_key` — the bank name normalized for matching (computed by the application; normalization rule: Ingestion Worker Functional Design), so variants such as `OCBC` / `OCBC Bank` can share a key
- `account_identifier` (nullable) — the account number **as printed on the statement** (Question 1 = B: full when the statement prints it in full, already masked when it prints it masked), normalized only for spacing and hyphens. Null when the statement prints none (A-2)
- `currency` (3-letter code)
- `created_at`

**Purpose**: The name an account has been *recognized by* on statements. An account starts with one key, created with it, and gains more only when a merge re-points an absorbed account's keys to the survivor (BR-35). The Account Resolver resolves an incoming statement by looking up its (`bank_key`, `account_identifier`, `currency`) here, never by matching on `Account` directly. Uniqueness is BR-30.

**Why a separate entity (found at this stage)**: if identity lived only on `Account`, a merge would fix only the statements that already exist, and the next statement printing the absorbed name (for example `POSB` after merging it into `DBS`, or `OCBC Bank` into `OCBC` — fragmentations already present in the live data) would resolve to a brand-new account and silently undo the merge. Keeping every key an account has been known by makes a merge permanent.

**Why currency is part of the key (refines FR-AB-2)**: a statement without a currency cannot commit (WR-2), so it is always available. Including it means one account number holding balances in several currencies resolves to one account *per currency* — what a per-currency balance needs — and no statement can ever be attached to an account of the wrong currency.

## Entity: StatementAccount (added 2026-10-03 — Account Balance at a Point in Time, Epic 13 Scope Change: several accounts per PDF)
- `id` (PK)
- `bank_statement_id` (FK -> BankStatement, required)
- `account_id` (FK -> Account, required)
- `closing_balance` (decimal(18,2), nullable) — the balance this account's section of the statement prints (FR-AB-5); may be negative for an overdrawn account
- `closing_balance_date` (date, nullable) — the date that balance applies to
- `created_at`

**Purpose**: One row per account a statement holds — the record that says "this statement contained this account, and printed this closing balance for it". A single-account PDF has exactly one. It carries the closing balance (together with its date or not at all, BR-33), is what a transaction links to (BR-38), and is how an account is tied to the statements it appears in. An account appears at most once per statement (BR-37): two sections of one PDF that turn out to be the same account are collapsed into one row by the Account Resolver before it gets here.

## Entity: BalanceAnchor (added 2026-10-02 — Account Balance at a Point in Time, Epic 13)
- `id` (PK)
- `account_id` (FK -> Account, **unique**) — BR-32
- `balance` (decimal(18,2); may be negative for an overdrawn account) — in the account's own currency (A-7)
- `as_of_date` (date)
- `created_at`
- `updated_at`

**Purpose**: The user's manual starting point for every balance computation on this account (FR-AB-6): a known real balance as of a specific date. At most one per account, replaced **in place** (A-6) — no history is kept, because US-13.3 needs the previous value shown before confirming, not retained, and the cross-check (FR-AB-8) is what catches a wrong anchor. The anchor survives a change of the account's type but is ignored while the account is not a deposit account (BR-32).

## Entity: KnownFile (added 2026-10-03 — Probable Duplicate Statement Detection, Epic 14)
- `id` (PK)
- `pdf_content_hash` (sha-256 hex digest of the file's bytes; **unique**) — BR-39
- `state` (enum: `probable_duplicate` | `overridden` | `confirmed_duplicate`) — BR-41
- `matched_statement_hash` (the content hash of the statement this file was judged a duplicate of; required, and never equal to `pdf_content_hash`) — BR-40
- `comparison_id` (FK -> DuplicateComparison, required) — BR-40
- `created_at`
- `updated_at`
- `decided_at` (nullable; set when the user overrides, BR-41)

**Purpose**: The remembered decision about one file, keyed by its content so renaming or re-uploading the same file changes nothing (A-PD-8). `probable_duplicate`: judged a duplicate at ingestion, or pre-registered by the Backfill Tool, and skipped without being read again (FR-PD-8, NFR-PD-2). `confirmed_duplicate`: a copy the user confirmed for removal, so the Drive file that remains is never re-ingested (FR-PD-13). `overridden`: the user said "not a duplicate", so the file is ingested on the next run and never flagged again (FR-PD-7). Read by the Duplicate Detection Component before extraction; written by the Probable Duplicate Detector, the Duplicate Review Component, the Statement Removal Handler, and the Backfill Tool. Refers to a statement by content hash and has no foreign key to `BankStatement` (BR-50).

## Entity: DuplicateComparison (added 2026-10-03 — Epic 14)
- `id` (PK)
- For each of two sides, **earlier** and **later** (the earlier-ingested statement, which is the original; and the later one, which is the skipped file or the later copy of a held pair): `<side>_content_hash`, `<side>_file_name` (nullable), `<side>_bank_name` (nullable), `<side>_period_start` (date), `<side>_period_end` (date), `<side>_transaction_count` (int, 0 or more) — twelve columns in all
- `matched_count` (int)
- `match_ratio` (decimal(5,4), 0 to 1) — matched transactions as a fraction of the smaller statement's transactions (FR-PD-3)
- `reason` (text) — the human-readable reason, for example "8 of 8 transactions match" (FR-PD-2)
- `created_at`

**Purpose**: The evidence for a flagged file or pair, stored at the moment of detection because a skipped file's transactions exist nowhere else (FR-PD-5) and so the view stays correct after the original is changed or removed (US-14.2). **Write-once** (BR-42). `<side>_file_name` is nullable because `bank_statements` stores no file name: it is resolved from the run file that processed the statement when the comparison is made, and stored here. Shared by up to several records: a skipped file's `KnownFile` and run file point at it; a held pair and, once the pair is resolved by a removal or a backfill, the `KnownFile` created from it point at the same row.

## Entity: DuplicateComparisonRow (added 2026-10-03 — Epic 14)
- `id` (PK)
- `comparison_id` (FK -> DuplicateComparison, required; rows are deleted with their comparison)
- `side` (enum: `earlier` | `later`)
- `rank` (int, 1 to 10; unique for a comparison and side) — 1 is the largest amount; ties are ranked earlier date first (Clarification Q1 = A)
- `transaction_date`
- `description` (text)
- `out_flow` (decimal(18,2), nullable) / `in_flow` (decimal(18,2), nullable) — exactly one is set and positive, the same convention as `Transaction` (BR-2)
- `currency` (3-letter) — the statement section's own currency, as printed; not converted
- `marker` (enum: `also_on_other` | `only_on_this_one`) — FR-PD-5

**Purpose**: One of the up to 10 largest transactions on one side of a comparison, with whether the other side also has it. A child table rather than a stored list so the database itself guarantees "at most 10 per side" (BR-42). Write-once with its comparison.

## Entity: DuplicatePair (added 2026-10-03 — Epic 14)
- `id` (PK)
- `hash_a` / `hash_b` (content hashes of the two held statements; `hash_a` is the smaller, so a pair is unordered) — BR-43
- `comparison_id` (FK -> DuplicateComparison, required)
- `keep_hash` (equal to `hash_a` or `hash_b`) — the worker's proposed copy to keep (FR-PD-11); the other is proposed for removal — BR-43
- `removal_allowed` (boolean, required; **added 2026-10-04, found at Ingestion Worker Functional Design Question 1 = C**) — whether the Review panel offers removal for this pair: true only when the two statements are of comparable size, so a larger statement that wholly contains a smaller one is listed for information only (dismiss, no remove) — BR-53
- `status` (enum: `pending` | `dismissed` | `removed` | `superseded`) — BR-44
- `found_at`
- `decided_at` (nullable)

**Purpose**: A probable-duplicate pair among statements already held (FR-PD-9), written by the worker's scan and listed in the Review page's panel. The proposal is computed once by the worker and stored (Application Design); manual-correction counts are not stored because they change as the user works. `dismissed` and `removed` are the memory that stops the pair being offered again (A-PD-5); `superseded` records that the backfill's reingest, or a later scan, made the pair moot. Refers to statements by content hash and has no foreign key to `BankStatement` (BR-50).

## Entity: StatementRemovalJob (added 2026-10-03 — Epic 14)
- `id` (PK)
- `pair_id` (FK -> DuplicatePair, required)
- `remove_statement_hash` (the content hash of the statement to delete; one of the pair's two)
- `corrections_acknowledged` (int, 0 or more) — how many manual corrections the user was told would be lost (NFR-PD-3)
- `status` (enum: `queued` | `running` | `embeddings_pending` | `embeddings_failed` | `completed` | `failed`) — see the lifecycle
- `failure_reason` (nullable text)
- `removed_transaction_ids` (list of ids, nullable; **no foreign key**, the rows are gone) — BR-46
- `deleted_counts` (nullable; the number of rows deleted, per kind)
- `embedding_attempts` (int, 0 or more)
- `requested_at`
- `started_at` (nullable)
- `finished_at` (nullable)

**Purpose**: A user-confirmed removal handed from the API Service to the Ingestion Worker (FR-PD-12/14, NFR-PD-4). Records exactly what the user acknowledged so the worker can refuse if the situation changed, and records the removed transactions' ids so their embeddings can be deleted after the database rows are gone. At most one active job per pair (BR-45). Finished jobs are kept (BR-47).

## Entity: DuplicateScanState (added 2026-10-03 — Epic 14)
- `id` (PK; fixed at 1) — BR-48
- `last_scan_started_at` (nullable)
- `last_scan_completed_at` (nullable)
- `last_scan_match_ratio` (decimal(5,4), nullable) — the match ratio the last scan used
- `last_scan_min_transactions` (int, nullable) — the small-statement minimum the last scan used
- `last_scan_pairs_found` (int, nullable)
- `recheck_requested_at` (nullable) — set by the API Service when the user asks for a re-check, or by the Backfill Tool when it finishes

**Purpose**: Backs the worker's "is a pair scan due" check and the panel's "last checked" line. The recorded ratio and minimum are how the worker notices that a detection setting has changed. Which exact conditions make a scan due is Ingestion Worker Functional Design.

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

Account (1) ----< AccountKey (via account_id)
Account (1) ---- (0..1) BalanceAnchor (via account_id, unique)
Account (1) ----< StatementAccount (via account_id)
BankStatement (1) ----< StatementAccount (via bank_statement_id)
StatementAccount (1) ----< Transaction (via statement_account_id, optional until backfilled)

DuplicateComparison (1) ----< DuplicateComparisonRow (via comparison_id)
DuplicateComparison (1) ----< KnownFile (via comparison_id)
DuplicateComparison (1) ----< DuplicatePair (via comparison_id)
DuplicateComparison (1) ----< IngestionRunFile (via duplicate_comparison_id, optional)
DuplicatePair (1) ----< StatementRemovalJob (via pair_id)
DuplicateScanState: a standalone single row
(KnownFile, DuplicatePair, and DuplicateComparison refer to statements by content hash only: no foreign key to BankStatement, StatementAccount, or Transaction, BR-50)
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
- One `Account` has one or more `AccountKey` rows (always at least one while it exists; more only after merges), at most one `BalanceAnchor`, and zero or more `StatementAccount` rows (one for each statement it appears in; zero for a newly created account momentarily, or after a backfill wipe until reingest). A transaction belongs to an account only through its `StatementAccount` link — `Transaction` has no direct account reference (revised 2026-10-03)
- One `AccountKey` belongs to exactly one `Account`, and no (`bank_key`, `account_identifier`, `currency`) triple appears on more than one key (BR-30)
- One `BankStatement` has one or more `StatementAccount` rows (one per account section; none only for statements ingested before the backfill), and at most one per account (BR-37). One `StatementAccount` has many `Transaction` rows (the transactions printed under that account), and each of them belongs to the same statement as the section (BR-38) (revised 2026-10-03)
- `Account`, `AccountKey`, and `BalanceAnchor` are the only entities the one-time backfill never wipes (BR-36)
- *(added 2026-10-03, Epic 14)* One `DuplicateComparison` has up to 10 `DuplicateComparisonRow` rows per side (BR-42) and may be referenced by several records: a `DuplicatePair`, the `KnownFile` created when that pair is resolved, and an `IngestionRunFile` that reported the skip. One `KnownFile` exists per content hash (BR-39). One `DuplicatePair` has zero or more `StatementRemovalJob` rows over time (a failed removal can be retried), at most one of them active (BR-45). A `IngestionRunFile` has a `duplicate_comparison_id` exactly when its outcome is `skipped_probable_duplicate` (BR-49).
- *(added 2026-10-03, Epic 14)* `KnownFile`, `DuplicatePair`, and the comparison are not wiped by the backfill and have no foreign key to anything the backfill wipes (BR-50, BR-36 addendum). `DuplicateScanState` is deliberately outside the diagram, a single standalone row like `BackupRun` and `SettingChange` are standalone logs.
