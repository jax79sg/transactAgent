# Business Rules — Unit 1: Database

Invariants and validation logic the data layer must enforce or support. Traced to requirements.md and stories.md.

## BR-1: Category Reference Integrity
Every `Transaction.category_id` MUST reference an existing `Category` row (active or inactive — soft-deleted categories remain valid FK targets for historical transactions). **Traces to**: FR-4.3, US-5.2 edge case.

## BR-2: Exactly One Flow Direction
Exactly one of `Transaction.out_flow` / `Transaction.in_flow` MUST be a non-null, positive value; the other MUST be null. A transaction cannot be simultaneously an inflow and outflow, nor neither. **Traces to**: FR-2.3, FR-4.1.

## BR-3: Statement Hash Uniqueness
`BankStatement.pdf_content_hash` MUST be unique across all rows. This is the enforcement point for duplicate-statement prevention. **Traces to**: FR-3.1, FR-3.2.

## BR-4: Category Name Uniqueness
`Category.name` MUST be unique across all rows (active and inactive) — prevents ambiguity if a removed category name is reused. **Traces to**: FR-4.3, Requirements Section 5.

## BR-5: UNSURE Category Is Reserved
Exactly one `Category` row has `is_reserved = true` and `name = 'UNSURE'`. This row MUST always have `active = true` and MUST NOT be deletable or renameable at the application layer (the schema marks it; enforcement of the deletion/rename block is an API Service concern, but the `is_reserved` flag is the data-layer signal it relies on). **Traces to**: FR-5.1, FR-5.2 (step 4), Requirements Section 5.

## BR-6: Inactive Categories Excluded From New Selection
A category with `active = false` MUST NOT be assignable to a transaction going forward (neither by auto-categorization nor manual correction), but MAY continue to be referenced by transactions that were assigned it before deactivation (BR-1). **Traces to**: US-5.2 edge case (Question 3 = B, soft delete).

## BR-7: FX Rate Cache Uniqueness
The combination of (`FxRateCache.from_currency`, `FxRateCache.to_currency`, `FxRateCache.rate_date`) MUST be unique — one cached rate per currency pair per date, supporting fetch-once/reuse caching. **Traces to**: FR-10.4.

## BR-8: Conversion Flag Consistency
- If `Transaction.conversion_unavailable = true`, then `Transaction.converted_amount_sgd` MUST be null and `Transaction.fx_rate_used_id` MUST be null.
- If `Transaction.conversion_is_approximate = true`, then `Transaction.fx_rate_used_id` MUST reference an `FxRateCache` row whose `rate_date` differs from `Transaction.transaction_date` (a fallback/nearest-prior-date rate, per FR-10.5).
- A transaction cannot have both `conversion_unavailable = true` and `conversion_is_approximate = true`.

**Traces to**: FR-10.5, US-3.7 edge cases, US-4.6.

## BR-9: Failed File Requires a Reason
Any `IngestionRunFile` with `outcome = 'failed'` MUST have a non-null `failure_reason`. **Traces to**: FR-2.5, US-1.5 edge case.

## BR-10: Single Active Ingestion Run
At most one `IngestionRun` may be in status `queued` or `running` at any given time (enforced via a partial unique constraint on status, or application-layer check backed by this invariant). A new trigger request while one is active MUST be rejected. **Traces to**: US-1.2 (implicit — one run must complete before another starts to keep progress reporting unambiguous).

## BR-11: Recategorization Jobs Only From Manual Corrections
`RecategorizationJob.source_transaction_id` MUST reference a `Transaction` whose `category_source = 'manual'` at the time the job is created (only manual corrections are precedent-worthy per FR-5.3/5.4 — auto-assigned categories, even if unedited, do not trigger this retroactive re-scan). **Traces to**: FR-5.4, US-3.4 edge case.

## BR-12: Skipped File Links to Existing Statement
An `IngestionRunFile` with `outcome = 'skipped_duplicate'` SHOULD reference the pre-existing `BankStatement` row it matched via `bank_statement_id`, so the UI can show "already processed as part of run X" rather than just "skipped". **Traces to**: US-1.4, US-1.5.

*Addendum (2026-10-03, Epic 14)*: a file skipped as a **probable** duplicate is a different case and does not use this link. It creates no statement, so it has no `bank_statement_id`; it links to its stored comparison instead (BR-49).

## BR-13: Monetary Precision
All monetary columns (`out_flow`, `in_flow`, `converted_amount_sgd`, `FxRateCache.rate` where applicable) use fixed-point decimal with 2 decimal places (Question 4 = A) — no floating-point storage, to avoid rounding drift across repeated aggregation. **Traces to**: NFR data-integrity expectations (implicit from FR-8 aggregate accuracy).

## BR-14: No Duplicate Pending Proposals (added 2026-08-02 — Epic 6)
For a given `(candidate_transaction_id, recategorization_job_id)` pair, at most one `RecategorizationProposal` row may exist with `status = 'pending'` at a time. **Traces to**: NFR-RR-2.

## BR-15: Proposal Candidate Excludes Its Own Source (added 2026-08-02 — Epic 6)
A `RecategorizationProposal.candidate_transaction_id` MUST NOT equal `RecategorizationJob.source_transaction_id` for the job it belongs to — a transaction cannot be proposed as a match for the very correction that triggered the search. **Traces to**: FR-RR-1, US-6.1 edge case.

## BR-16: Proposals Are Resolved Exactly Once (added 2026-08-02 — Epic 6)
A `RecategorizationProposal` may only transition out of `pending` once (to `approved` or `rejected` by a user action, or to `auto_applied` at creation time — never both created-as-pending-then-auto-applied). Approving or rejecting a proposal that is not currently `pending` MUST be rejected as an error, not silently accepted. **Traces to**: FR-RR-7, FR-RR-8, US-6.4 edge case (prevents double-processing under concurrent bulk actions).

## BR-17: One Backup Attempt Per Calendar Day (added 2026-08-08 — Epic 7)
`BackupRun.backup_date` MUST be unique across all rows — at most one attempt (success or failure) per calendar day. This single constraint backs both "don't run a duplicate backup the same day" (US-7.1 edge case) and "don't auto-retry a failed backup the same night" (FR-9, US-7.4 edge case): once a row exists for a given date, no further attempt is made until the next calendar day. **Traces to**: FR-1, FR-9.

## BR-18: Failure Category Requires Failed Outcome (added 2026-08-08 — Epic 7)
`BackupRun.failure_category` MUST be null when `outcome = 'success'`, and MUST be one of `drive_connectivity` | `other` when `outcome = 'failed'`. This is the data-layer signal the Backup Status Component relies on to choose which message to show (reconnect-Drive prompt vs. generic failure indicator). **Traces to**: FR-10, FR-11.

## BR-19: Annual Recurring Payment Requires a Due Month (added 2026-08-08 — Epic 8)
`RecurringPayment.due_month` MUST be non-null when `frequency = 'annual'`, and MUST be null when `frequency = 'monthly'`. **Traces to**: FR-1.

## BR-20: Due Day Range (added 2026-08-08 — Epic 8)
`RecurringPayment.due_day` MUST be between 1 and 31 inclusive. Short-month edge cases (e.g. a due day of 31 in a 30-day month) are an application-layer concern (Ingestion Worker's due-date window calculation), not a data-layer one. **Traces to**: FR-1.

## BR-21: At Most One Live Match Per Recurring Payment Per Cycle (added 2026-08-08 — Epic 8)
For a given `(recurring_payment_id, cycle_period)` pair, at most one `RecurringPaymentMatch` row may have `status IN ('pending', 'approved', 'auto_applied')` at a time — enforced via a raw-SQL partial unique index, same pattern as BR-10 (`ingestion_runs`) and BR-14 (`recategorization_proposals`). A `rejected` row does not count, so a different transaction can still be proposed for the same cycle later (FR-8 leaves the door open; nothing is permanently suppressed). **Traces to**: FR-5, FR-6, FR-8.

## BR-22: Detection Pattern Uniqueness (added 2026-08-08 — Epic 8)
`DetectionSuggestion.description_pattern` MUST be unique across all rows — the entire enforcement mechanism behind FR-13's "a dismissed suggestion never reappears": one row exists per pattern for the lifetime of the database, and its `status` transitions rather than a new row being inserted on every re-scan. **Traces to**: FR-12, FR-13.

## BR-23: Matches Resolve Exactly Once (added 2026-08-08 — Epic 8)
A `RecurringPaymentMatch` may only transition out of `pending` once (to `approved`/`rejected` by a user action, or created directly as `auto_applied` — never both). Approving or rejecting a match that is not currently `pending` MUST be rejected as an error, not silently accepted — same pattern as BR-16. Application-layer enforced (Unit 2). **Traces to**: FR-6, FR-7, FR-8.

## BR-24: Embedding Status Is One-Way, Two-State (added 2026-08-11 — Local Embedding-Based Semantic Similarity, Epic 9)
`Transaction.embedding_status` only ever transitions `pending` -> `completed`, exactly once, written by the Ingestion Worker's Embedding Manager Component after it successfully computes and persists the transaction's embedding to the Vector DB. There is no `failed` state: a transient failure (endpoint unavailable, per FR-10) simply leaves the row `pending` for a later poll cycle to retry — this keeps the retry logic uniform (every `pending` row is always eligible, no separate failure/backoff bookkeeping) and matches FR-10's framing of a failure as "no embedding yet," not a distinct error condition the user needs to see differently from "not processed yet." Every new `Transaction` row (whether newly-ingested or pre-existing at migration time, FR-11) starts `pending` by default — this single default is what makes forward processing and the one-time historical backfill the same mechanism (see `domain-entities.md`'s Transaction addendum). Application-layer enforced (Unit 3, Embedding Manager Component). **Traces to**: FR-6, FR-7, FR-10, FR-11, NFR-4.

## BR-25: RecurringPayment Embedding Status Resets on Rename (added 2026-08-12, retroactively during Ingestion Worker Service Functional Design — Local Embedding-Based Semantic Similarity, Epic 9)
`RecurringPayment.embedding_status` follows the same one-way `pending` -> `completed` transition as BR-24, written to `completed` by the Ingestion Worker's Embedding Manager Component — but unlike `Transaction`, this field has a second write path: the API Service's Recurring Payments Component MUST (re)set it to `pending` whenever a `RecurringPayment` row is created OR its `name` is updated (FR-1 CRUD). This is what keeps the vector store's `recurring_payment_names` collection from silently going stale after a rename — the resolved answer to the Ingestion Worker Service Functional Design's Question 1 (Option A) requires this reset to actually deliver on "one unified, always-eventually-consistent mechanism," since a rename with no reset would otherwise leave `matchNewTransaction`/`runDetectionScan` matching forever against the old name's embedding. A `RecurringPayment` update that does not change `name` (e.g. `expected_amount`, `due_day`, `category_id`) MUST NOT reset `embedding_status` — no re-embedding is needed since the text being embedded hasn't changed. Application-layer enforced (Unit 2's Recurring Payments Component for the `pending` write path, Unit 3's Embedding Manager Component for the `completed` write path). **Traces to**: FR-1, FR-6, FR-10, FR-11, NFR-4.

## BR-26: LLM Suggested Category Is Write-Once (added 2026-08-16 — Matching Precision Refinement)
`Transaction.llm_suggested_category_id` is written exactly once, at the same time the transaction row is first persisted during ingestion (FR-MPR-1) — either to a real category (the LLM's classification) or left `null` (the LLM abstained with `UNSURE`, or its endpoint was unreachable, FR-MPR-1/NFR-MPR-2). It is never updated afterward by any later event — not a manual correction, not a proposal approval, not a disagreement resolution (BR-27) — since its entire purpose is preserving a historical record of what the LLM independently believed at ingestion time, for the retroactive re-scan's score-boost logic (FR-MPR-7) to read back later. Unlike `category_id` (mutable, reflects the transaction's current, actual category), this field is immutable once set. Application-layer enforced (Unit 3, Categorization Engine Component). **Traces to**: FR-MPR-1, FR-MPR-7.

## BR-27: Disagreement Resolution Must Be One of the Two Offered Candidates (added 2026-08-16 — Matching Precision Refinement)
`CategorizationDisagreement.resolved_category_id`, when set, MUST equal either `similarity_category_id` or `llm_category_id` on that same row — never a third, unrelated category. This is what "pick one of the two" (FR-MPR-10/11) actually means at the data layer: the human is choosing between two system-computed suggestions, not entering a free choice (a free choice is still available via the plain `UNSURE`-category correction dropdown, unaffected by this feature). Same one-time-resolution shape as BR-16 (`RecategorizationProposal`) and BR-23 (`RecurringPaymentMatch`) — a `CategorizationDisagreement` may only transition out of `pending` once, to either `resolved` (with one of the two candidates written to both `resolved_category_id` and the transaction's own `category_id`) or `rejected` (transaction left `UNSURE`, no suppression record kept, same policy as BR-16/FR-RR-8). Application-layer enforced (Unit 2, Recategorization Review Component). **Traces to**: FR-MPR-9, FR-MPR-10, FR-MPR-11.

## BR-28: SettingChange Rows Are Append-Only (added 2026-08-16 — Configurable Application Settings)
Once written, a `SettingChange` row is never updated or deleted — every subsequent change to the same `setting_name` inserts a new row rather than modifying an existing one. This is what makes `listSettingHistory()` (FR-CAS-9, US-10.4) a trustworthy historical record rather than a mutable "current state" table (which `previous_value`/`new_value` on the *latest* row alone would not be, once more than one change has happened). Application-layer enforced (Unit 2, Configuration Component — no `UPDATE`/`DELETE` code path is ever written against this table). **Traces to**: FR-CAS-9, NFR-CAS-6.

## BR-29: Setting Name Is Restricted to the Application-Layer Allow-List, Not a DB Constraint (added 2026-08-16 — Configurable Application Settings)
`SettingChange.setting_name` is a plain string column with no DB-level `CHECK`/enum/FK constraint tying it to the 40 in-scope settings (corrected from an original miscount of 35 -- see requirements.md's Post-Approval Change section). The allow-list is owned entirely by the API Service's Configuration Component (Application Design's "Component Boundary Note") — the same allow-list `updateSetting()` already consults before any row is written, so in practice no `SettingChange` row can exist for a name outside it, but that guarantee comes from the application layer, not the schema. This mirrors this project's existing precedent of keeping business-meaning constraints (e.g. `extraction_confidence_threshold`'s low/medium/high values in `config.py`) out of the database when the authoritative list already lives in code. **Traces to**: NFR-CAS-2, NFR-CAS-4.

## BR-30: Account Key Uniqueness (added 2026-10-02 — Account Balance at a Point in Time, Epic 13)
At most one `AccountKey` row may exist for any (`bank_key`, `account_identifier`, `currency`) combination, and a **missing identifier counts as its own distinct value**: two keys with the same `bank_key` and `currency` and no identifier cannot coexist, while a key with an identifier and one without never conflict. This is what makes account resolution deterministic: an incoming statement's key matches at most one account. **DB-enforced** (a uniqueness guarantee that treats an absent identifier as a value, not as "unknown"; exact mechanism is Code Generation). **Traces to**: FR-AB-2, US-13.1.

## BR-31: Account Currency Is Fixed (added 2026-10-02 — Epic 13)
`Account.currency` is set when the account is created and never changed afterward, and every `AccountKey` belonging to an account carries that same currency. Two accounts of different currencies can therefore never be merged (BR-35), and a statement can never resolve to an account of a different currency, because currency is part of the key (BR-30). **Application-layer enforced** (Unit 2, Account Management Component; Unit 3, Account Resolver Component) — a cross-table equality a single-table constraint cannot express. **Traces to**: A-6, US-13.2 (merge refused on currency mismatch).

## BR-32: One Anchor Per Account, Inert Unless the Account Is a Deposit Account (added 2026-10-02 — Epic 13)
An account has **at most one** `BalanceAnchor` (**DB-enforced** unique `account_id`); setting a new anchor replaces the existing row in place (A-6). An anchor's `as_of_date` must not be in the future at the moment it is set — **application-layer enforced**, not a database constraint, because "not in the future" depends on today's date, which a constraint cannot evaluate reliably (same reasoning as BR-14..16's application-layer time-relative rules). An anchor attached to an account whose `account_type` is not `deposit` is **kept but ignored**: no balance computation reads it, and no anchor can be *created* for such an account, but changing a deposit account to another type does not delete its anchor, so switching back restores it. **Traces to**: FR-AB-6, FR-AB-4, A-6, A-7, US-13.3.

## BR-33: Closing Balance and Its Date Come Together (added 2026-10-02 — Epic 13)
On a `StatementAccount` (moved here from `BankStatement` on 2026-10-03 with the several-accounts-per-PDF Scope Change), `closing_balance` and `closing_balance_date` are either **both null or both non-null**. A balance with no date, or a date with no balance, cannot be cross-checked (FR-AB-8), so the pair is never stored half-populated. **DB-enforced** (a row-level `CHECK`, same family as BR-2's and BR-8's). **Traces to**: FR-AB-5, US-13.6.

## BR-34: A User-Set Account Type Is Never Overwritten (added 2026-10-02 — Epic 13)
When the user corrects an account's type through the Account Management Component, `Account.type_user_set` becomes true and stays true. From then on no extraction result — however many later statements for that account say otherwise — may change `account_type`. While `type_user_set` is false, the Ingestion Worker's Account Resolver may set the type from extraction (including moving it from `unknown` to a known value); the precise rule for a later extraction that disagrees with an earlier one is Ingestion Worker Functional Design. **Application-layer enforced** (Unit 3, Account Resolver Component; Unit 2, Account Management Component sets the flag). **Traces to**: FR-AB-3, A-3, US-13.2.

## BR-35: Merge Is All-or-Nothing and Permanent (added 2026-10-02 — Epic 13)
Merging account A (absorbed) into account B (survivor) is a single indivisible operation: (1) it is refused unless A and B have the same currency (BR-31) **and no single statement has a `StatementAccount` for both** (a statement that lists both proves they are different accounts — added 2026-10-03; this is also what keeps BR-37 from being violated by step 3); (2) if both have an anchor, the caller must choose which one survives and the other is deleted — if only one has an anchor, that one ends up on B; (3) every `StatementAccount` of A is re-pointed to B (revised 2026-10-03; transactions follow automatically, since they link to the section); (4) every `AccountKey` of A is re-pointed to B, so future statements that A used to match now resolve to B (BR-30 cannot be violated by this, since keys are unique across all accounts); (5) A is deleted. B's name, type, and `type_user_set` are unchanged: the survivor wins, and the user can correct afterwards. If any step fails, nothing changes. An `Account` can only be deleted once it has no statement sections, no keys, and no anchor — **DB-enforced** by restricting deletion of a referenced account — so the merge procedure's ordering (re-point first, delete last) is also what the schema requires; the all-or-nothing and anchor-choice parts are **application-layer enforced** (Unit 2, Account Management Component). **Traces to**: FR-AB-3, A-6, US-13.2.

## BR-36: What the One-Time Backfill Wipes, Keeps, and Detaches (added 2026-10-02 — Epic 13)
The backfill (US-13.7) treats data in three groups, so it is safe to run more than once:
- **Wiped** (in this order, since each depends on the next): `recurring_payment_matches`, `categorization_disagreements`, `recategorization_proposals`, `recategorization_jobs`, then `transactions`, then `statement_accounts` (added 2026-10-03), then `bank_statements`. *Refined 2026-10-03 (Ingestion Worker Functional Design)*: a statement whose source PDF is missing from Drive is **not wiped at all** — it, its sections, its transactions, and their dependents stay exactly as they are — since it could never be re-created; the wipe covers every statement that can be re-ingested.
- **Detached, not deleted**: `ingestion_run_files.bank_statement_id` (already nullable, BR-12) is set to null for every row referencing a wiped statement, so past ingestion run history survives.
- **Kept untouched**: `accounts`, `account_keys`, and `balance_anchors` — so re-running the backfill never loses a merge, a rename, a corrected type, or an anchor — plus `categories`, `recurring_payments`, `detection_suggestions`, `detection_scan_runs`, `users`, `oauth_credentials`, `setting_changes`, `backup_runs`, `fx_rate_cache`, and `ingestion_runs`/`ingestion_run_logs`. Reingested statements resolve through the kept `account_keys` to the same accounts, so anchors apply to them immediately.
Because the wipe deletes the `BankStatement` row that BR-3 and the Statement Processing Idempotency rule check against, the same PDFs are treated as new on the next run — that is the mechanism the backfill relies on, not a bypass of duplicate detection. **Application-layer enforced** (Unit 3, Backfill Tool Component). **Traces to**: FR-AB-15, FR-AB-16, FR-AB-17, NFR-AB-2, US-13.7.

*Addendum (2026-10-03, Epic 14)*: the backfill's data handling is extended to the entities Probable Duplicate Statement Detection adds. `known_files`, `duplicate_comparisons`, `duplicate_comparison_rows`, `duplicate_pairs`, `statement_removal_jobs`, and `duplicate_scan_state` are **never wiped and never detached**: they hold decisions the user made, they refer to statements by content hash (BR-50), and none has a foreign key to a table in the wipe order, so the wipe order above is unchanged. The backfill **adds** `known_files` rows and marks the pending pairs its reingest resolves `superseded` (BR-44). All of these tables are part of the backfill's backup and restore set, because it modifies them and `restore` must be able to put them back. **Application-layer enforced** (Unit 3, Backfill Tool Component). **Traces to**: FR-PD-16, FR-PD-17, NFR-PD-5.

## BR-37: An Account Appears at Most Once per Statement (added 2026-10-03 — Epic 13 Scope Change: several accounts per PDF)
A statement has at most one `StatementAccount` row for any given account: the pair (`bank_statement_id`, `account_id`) is unique. A statement holds several *different* accounts, never the same one twice. If extraction returns two sections that resolve to the same account (same bank key, identifier, and currency), the Account Resolver collapses them into one before anything is stored; this rule is the schema's backstop. **DB-enforced** (unique constraint). **Traces to**: FR-AB-2, US-13.1 ("same account twice in one PDF"), BR-35 (why a merge of two co-occurring accounts is refused).

## BR-38: A Transaction's Statement Section Belongs to Its Own Statement (added 2026-10-03 — Epic 13 Scope Change)
When `Transaction.statement_account_id` is set, the `StatementAccount` it points to must belong to the **same `BankStatement`** as `Transaction.bank_statement_id`. This prevents a transaction from being linked to a section of some other statement, which would silently attribute it to the wrong account and corrupt that account's balance. **DB-enforced** by a composite foreign key from (`transactions.bank_statement_id`, `transactions.statement_account_id`) to (`statement_accounts.bank_statement_id`, `statement_accounts.id`) — which requires that pair to be unique on `statement_accounts` — and inert while `statement_account_id` is null (a null column in a composite foreign key skips the check), which is exactly the pre-backfill state. **Traces to**: FR-AB-1, FR-AB-7, US-13.1.

## BR-39: A Content Hash Has At Most One Remembered Record (added 2026-10-03 — Probable Duplicate Statement Detection, Epic 14)
`KnownFile.pdf_content_hash` is unique: a file's content has one remembered decision at a time (skipped, overridden, or removed), never two that could disagree. **DB-enforced** (unique constraint). **Traces to**: FR-PD-8, FR-PD-13, A-PD-8.

## BR-40: A Remembered Record Always Carries Its Evidence (added 2026-10-03 — Epic 14)
Every `KnownFile`, whatever its state, has a `matched_statement_hash` that differs from its own `pdf_content_hash`, and a `comparison_id` referencing an existing comparison. So a run result can always link to the evidence (US-14.2, US-14.4), and the Backfill Tool can always carry manual corrections from a skipped copy to the copy that was kept (FR-PD-17). **DB-enforced** (not-null columns, a foreign key, and a row-level `CHECK`). **Traces to**: FR-PD-2, FR-PD-5, FR-PD-17.

## BR-41: Remembered-File Changes Are One-Way (added 2026-10-03 — Epic 14)
A `KnownFile` is inserted as `probable_duplicate` (skipped at ingestion, or pre-registered by the Backfill Tool) or as `confirmed_duplicate` (a removal completed). The only change afterward is to `overridden`, from either state, which sets `decided_at`; `overridden` is final. A user can therefore always bring a skipped file in, and can bring a *removed* copy back by re-ingesting its Drive file (the corrections that sat on it are not restored), but a decision is never silently reversed by the system. **Application-layer enforced** (Unit 2 Duplicate Review Component; Unit 3 Probable Duplicate Detector, Statement Removal Handler, Backfill Tool), since a database `CHECK` cannot constrain a transition. **Traces to**: FR-PD-7, FR-PD-13, A-PD-4, NFR-PD-5.

## BR-42: A Comparison Is Write-Once and Bounded (added 2026-10-03 — Epic 14)
A `DuplicateComparison` and its rows are written once and never updated, so the evidence stays what it was at detection (US-14.2). The database enforces the bounds: transaction counts are zero or more; `matched_count` is between 0 and the smaller of the two sides' counts; `match_ratio` is between 0 and 1; each row has a `rank` from 1 to 10 that is unique for its comparison and side, so a side can never hold more than 10 rows (FR-PD-5); and each row has exactly one positive flow (BR-2's convention). **DB-enforced** (row-level `CHECK`s and a unique constraint); the write-once property is **application-layer enforced**. **Traces to**: FR-PD-5, FR-PD-6, US-14.2.

## BR-43: A Pair Is Unordered and Unique (added 2026-10-03 — Epic 14)
A `DuplicatePair` stores its two content hashes with `hash_a` smaller than `hash_b`, and the pair (`hash_a`, `hash_b`) is unique, so the same two statements can be recorded only once whichever way round they were found. `keep_hash` is one of the two. **DB-enforced** (`CHECK` and unique constraint). **Traces to**: FR-PD-9, FR-PD-11, A-PD-5.

## BR-44: A Decided or Superseded Pair Is Never Reopened (added 2026-10-03 — Epic 14)
The scan only inserts a pair when no row exists for those two hashes, refreshes a `pending` pair's proposal and comparison, and marks a `pending` pair `superseded` when its two statements are no longer both held. `dismissed`, `removed`, and `superseded` are final, which is what stops a pair the user rejected, or one already removed, from being offered again. A file whose `KnownFile` state is `overridden` is excluded from the scan on either side. **Application-layer enforced** (Unit 3, Probable Duplicate Detector). **Traces to**: FR-PD-10, A-PD-5.

## BR-45: One Active Removal Job Per Pair (added 2026-10-03 — Epic 14)
A pair has at most one removal job in `queued`, `running`, or `embeddings_pending` at a time, so a double confirmation cannot delete a statement twice. A `failed` or `embeddings_failed` job does not count, which is what lets the user retry. **DB-enforced** (a unique constraint limited to the active statuses). **Traces to**: FR-PD-14, US-14.6.

## BR-46: A Removal Records Its Transactions Before Their Embeddings Are Deleted (added 2026-10-03 — Epic 14)
Once the database rows are deleted, the transactions' ids can no longer be looked up, and their embeddings still exist. So the deletion and the move to `embeddings_pending` happen in **one transaction**, which also records `removed_transaction_ids`; the worker then deletes the embeddings and moves the job to `completed`. A job in `embeddings_pending` or `embeddings_failed` must have `removed_transaction_ids`, and a job in `failed` or `embeddings_failed` must have a `failure_reason` (BR-9's family). `embeddings_failed` is where a job is parked after bounded retries; it leaves only orphaned vectors, harmless to the database. **DB-enforced** (`CHECK`s); the single-transaction ordering is **application-layer enforced** (Unit 3, Statement Removal Handler). **Traces to**: FR-PD-12, FR-PD-14, NFR-PD-3, NFR-PD-4.

## BR-47: Removal Jobs Are Kept (added 2026-10-03 — Epic 14)
A `StatementRemovalJob` is never deleted after it finishes. It is the permanent record of a permanent deletion: what was removed, how many rows of each kind, what the user acknowledged, and when. The same append-only reasoning as BR-28 for `SettingChange`. **Application-layer enforced**. **Traces to**: NFR-PD-3.

## BR-48: Scan State Is a Single Row (added 2026-10-03 — Epic 14)
`DuplicateScanState` holds exactly one row, with a fixed `id` of 1. A second row cannot exist, so there is one answer to "when did the last scan run and with which settings". **DB-enforced** (`CHECK` on the id). **Traces to**: FR-PD-9.

## BR-49: A Probable-Duplicate Skip Carries Its Comparison and No Statement (added 2026-10-03 — Epic 14)
An `IngestionRunFile` has a `duplicate_comparison_id` **if and only if** its `outcome` is `skipped_probable_duplicate`, and such a row has no `bank_statement_id` (it created no statement). Every other outcome keeps its existing rules (BR-9, BR-12). **DB-enforced** (row-level `CHECK`s). **Traces to**: FR-PD-1, FR-PD-2, NFR-PD-6.

## BR-50: The New Entities Refer to Statements by Content Hash Only (added 2026-10-03 — Epic 14)
`KnownFile`, `DuplicatePair`, and `DuplicateComparison` identify a statement by its `pdf_content_hash`, never by a row id, and no new table has a foreign key to `bank_statements`, `statement_accounts`, or `transactions`. The reason: the backfill deletes and recreates every statement with a new id, and a removal deletes a statement outright; a row-id link would block both, and a hash stays valid across them. The consequence is that the reference is resolved when read, and a hash with no current statement simply means that statement is gone. **Guaranteed by schema** (no such foreign key exists) and checked by the guard test in BR-51. **Traces to**: FR-PD-13, FR-PD-16, FR-PD-17, NFR-PD-5.

## BR-51: One List of What Depends on a Statement (added 2026-10-03 — Epic 14)
Three places must agree on which rows depend on a statement's transactions: the Statement Removal Handler (what it deletes), the Backfill Tool's wipe (BR-36), and the API Service's removal preview (the counts the user is shown before confirming, FR-PD-12). The dependents today, checked against the real table metadata on 2026-10-03, are: deleted first, in this order, `recurring_payment_matches`, `categorization_disagreements`, `recategorization_proposals`, and `recategorization_jobs` (each with a foreign key to `transactions`), then `transactions`, then `statement_accounts`, then `bank_statements`; and **detached rather than deleted**, `ingestion_run_files.bank_statement_id` (set to null, BR-12 and BR-36). A guard test in this unit reads the table metadata and **fails if any table outside that list has a foreign key to `transactions`, `statement_accounts`, or `bank_statements`**, so a future feature that adds a dependent table cannot silently be missed by the removal, the wipe, or the preview. None of the six Epic 14 tables has such a key (BR-50), which the same test confirms. **Test-enforced** (Unit 1 tests). **Traces to**: FR-PD-12, NFR-PD-3.

## BR-52: A Probable-Duplicate Skip Is Not a Failure (added 2026-10-03 — Epic 14)
A file with outcome `skipped_probable_duplicate` counts in the run's `files_skipped_count`, like an exact-duplicate skip, and never makes a run `completed_with_failures`. **Application-layer enforced** (Unit 3, Ingestion Orchestrator). **Traces to**: FR-PD-2, NFR-PD-6.

## BR-53: Removal Is Offered Only for Pairs of Comparable Size (added 2026-10-04 — Epic 14, found at Ingestion Worker Functional Design Question 1 = C)
Every `DuplicatePair` carries `removal_allowed`. It is true only when the smaller statement has at least `duplicate_match_ratio` times the larger one's transactions; otherwise the pair is listed for information only, with a dismiss action and no remove action, so a statement is never removed when the other lacks some of its transactions on a large scale. The Ingestion Worker computes and stores it (refreshed by each scan); the API Service displays it and **refuses to create a removal job** for a pair where it is false, and the Statement Removal Handler re-verifies it before deleting. The column is required with no default, so a writer must decide it. **Application-layer enforced** for the rule itself; the column's presence is **DB-enforced** (not null). **Traces to**: FR-PD-10, FR-PD-12, NFR-PD-3.
