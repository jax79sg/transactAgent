# Business Logic Model — Unit 1: Database

Schema-relevant lifecycle and state-transition logic. This unit has no runtime service, but the valid state machines below constrain what other units (API Service, Ingestion Worker Service) are allowed to write, and are therefore part of this unit's functional design.

## State Machine: IngestionRun.status

```
queued --> running --> completed
                    \-> completed_with_failures
                    \-> failed
```

- **queued**: Created by the API Service (Unit 2) when the user triggers a run (US-1.2); BR-10 ensures only one run is ever in `queued` or `running`.
- **running**: Claimed by the Ingestion Worker Service (Unit 3) polling for queued runs.
- **completed**: All files in the run had outcome `processed`, `skipped_duplicate`, or `skipped_probable_duplicate` (zero `failed`; a skip is never a failure, BR-52).
- **completed_with_failures**: At least one file had outcome `failed`, but the run itself finished (NFR-2.2 partial-failure isolation — one bad file does not abort the run).
- **failed**: A run-level failure occurred before any per-file processing could complete (e.g., Drive auth failure per US-1.1 edge case) — distinct from a per-file `failed` outcome.

No transition skips a state (e.g., `queued` never jumps directly to `completed`).

## State Machine: IngestionRunFile.outcome

```
(created when file is listed) --> processed
                               --> skipped_duplicate
                               --> skipped_probable_duplicate   (added 2026-10-03, Epic 14)
                               --> failed
```

`skipped_duplicate` means the file's exact bytes were already processed (the existing statement is linked, BR-12). `skipped_probable_duplicate` means different bytes whose extracted transactions match a statement already held, or a file already remembered as such: no statement exists for it, and its stored comparison is linked instead (BR-49). Terminal, single-assignment — set once when the Orchestrator finishes handling that file, never revised afterward (a genuinely-changed statement per FR-3.2's edge case is a **new** `IngestionRunFile`/`BankStatement` row, not a mutation of the old one).

## Lifecycle: Transaction.category_source

```
(created) --> similarity | llm | unsure   [set once, at extraction/categorization time]
                    |
                    v (only via explicit user action, US-3.4)
                 manual
```

- Initial value is set exactly once when the transaction is first persisted by the Ingestion Worker Service, per the FR-5.2 fallback chain (similarity match found -> `similarity`; no match, LLM succeeds -> `llm`; neither confident -> `unsure`).
- The only further transition is to `manual`, triggered by a user correction (US-3.4). Once `manual`, the category can still be changed again by the user (still `manual`), but auto-categorization logic never overwrites a `manual` category_source for that same transaction — it only ever reads manual transactions as precedent for *other* transactions (FR-5.3).
- **Addendum (2026-08-16, Matching Precision Refinement)**: `categorize()`'s FR-5.2 chain is refined by FR-MPR-6 — a similarity/LLM agreement still yields `similarity` (unchanged); one confident signal with the other abstaining yields whichever source was confident (`similarity` or `llm`, same as today); a genuine disagreement leaves `category_source = unsure` (no different from today's plain-UNSURE case) until a human resolves the resulting `CategorizationDisagreement` row, at which point it transitions to `similarity` or `llm` depending on which candidate was picked (BR-27) — never `manual`, since the human chose between two system suggestions rather than typing a category from scratch. This is a new fifth transition into the diagram above: `unsure` -(disagreement resolved)-> `similarity`|`llm`, distinct from the existing `unsure`-(user correction)->`manual` path. `llm_suggested_category_id` (BR-26) is a separate, independent field — it never drives `category_source` and is never itself displayed as the transaction's category.

## Lifecycle: RecategorizationJob.status

```
queued --> running --> completed
                    \-> failed
```

- **queued**: Created by the API Service (Unit 2) immediately after a `Transaction.category_source` transitions to `manual` (BR-11 — only created for manual corrections).
- **running**: Claimed by the Ingestion Worker Service's Categorization Engine.
- **completed**: `updated_transaction_count` is set to the number of `UNSURE` transactions that were re-evaluated and changed.
- **failed**: An error occurred (e.g., transient DB issue) — per NFR-2.2-style resilience, a failed recategorization job does not affect the correctness of the original manual correction, which is already persisted independently.

## Lifecycle: RecategorizationProposal.status (added 2026-08-02 — Epic 6)

```
                 (found during broadened search, FR-RR-1)
                              |
              +---------------+---------------+
              |                               |
   [UNSURE candidate,                [categorized candidate,
    score >= auto-apply                any score, OR
    threshold]                         UNSURE below auto-apply
              |                        threshold]
              v                               v
        auto_applied                       pending
     (Transaction updated                    |
      immediately, no                +-------+-------+
      review needed)                 |               |
                                      v               v
                                  approved         rejected
                             (Transaction        (Transaction
                              updated on          left untouched,
                              user action)         no memory kept)
```

- Every proposal starts life already decided as `auto_applied`, or starts as `pending` — never the reverse (BR-16). The branch is decided once, at creation time, by which bucket the candidate came from and its match score (Application Design: Categorization Engine addendum).
- `pending` is the only status the Recategorization Review Component's list/count queries ever return (US-6.4/US-6.6) — `auto_applied`, `approved`, and `rejected` rows remain in the table as a historical record but never appear as an action item.
- Rejection intentionally has no further state — there is no "permanently suppressed" status, per FR-RR-8's explicit no-memory decision (US-6.5). A future correction can generate a fresh `pending` proposal for the same candidate+category combination.

## Lifecycle: CategorizationDisagreement.status (added 2026-08-16 — Matching Precision Refinement)

```
   (categorize() finds both similarity AND LLM
    confident, and they differ — FR-MPR-6/9)
                    |
                    v
                 pending
                    |
          +---------+---------+
          |                   |
          v                   v
       resolved             rejected
  (transaction updated   (transaction left
   to whichever of the    UNSURE, no memory
   two candidates the     kept -- BR-27/
   user picked --          FR-RR-8 policy)
   BR-27)
```

- Unlike `RecategorizationProposal`, every `CategorizationDisagreement` starts life `pending` — there is no creation-time `auto_applied` branch, since a genuine disagreement (by definition, FR-MPR-6's third bullet) is exactly the case where the system deliberately does not pick a side.
- `pending` is the only status the Recategorization Review Component's disagreement list/count queries return, same convention as `RecategorizationProposal.status`.
- Rejection has no further state, same no-memory policy as `RecategorizationProposal` (FR-RR-8) — a future ingestion of a similarly-described transaction can generate a fresh `pending` disagreement independently.

## Lifecycle: BackupRun (added 2026-08-08 — Epic 7)

Unlike `IngestionRun.status` and `RecategorizationJob.status` above, `BackupRun` has no `queued`/`running` interim state and no state machine to diagram:

```
(nothing) --> [backup attempt runs synchronously within one Ingestion Worker poll cycle] --> success | failed
```

- `IngestionRun`/`RecategorizationJob` need an interim status because they coordinate *across* services — the API Service inserts a `queued` row, and the Ingestion Worker Service claims and updates it asynchronously, from a separate process, at a separate time (`services.md`'s Cross-Service Coordination pattern).
- A `BackupRun` attempt has no such handoff: it is entirely synchronous within a single Ingestion Worker poll cycle (Application Design `services.md` addendum — `poll_once()`'s third branch calls `Backup Manager.runBackup()` directly, to completion, before the cycle ends). Nothing else claims it mid-flight, so there is nothing for an interim status to represent.
- The row is therefore written exactly once, already in its terminal state (`success` or `failed`, BR-17/BR-18), at the moment the attempt finishes — not created early and updated later.
- `Backup Status Component.getLatestBackupStatus()` (API Service) simply reads the most recent `BackupRun` row by `backup_date` — there is never a "backup in progress" state for it to observe or display.

## Lifecycle: RecurringPaymentMatch.status (added 2026-08-08 — Epic 8)

```
                 (found by Recurring Payment Manager, FR-5)
                              |
              +---------------+---------------+
              |                               |
   [never-yet-approved payment,       [trusted payment,
    OR amount outside tolerance]       amount within tolerance]
              |                               |
              v                               v
          pending                       auto_applied
              |                       (cycle marked Paid
     +--------+--------+               immediately, no
     |                 |               review needed)
     v                 v
  approved          rejected
(cycle marked      (transaction
 Paid; payment's    left untouched,
 is_trusted set     no memory kept —
 to true)           may be re-proposed
                     later, BR-21)
```

- Structurally the same shape as `RecategorizationProposal.status` (Epic 6) — the branch is decided once, at creation time, by whether the owning `RecurringPayment` is already trusted and how close the matched amount is (FR-6/FR-7, Application Design: Recurring Payment Manager).
- `pending` is the only status the Recurring Payments Component's review list ever returns as an action item — `approved`/`rejected`/`auto_applied` rows remain as historical record.
- Unlike Epic 6's proposals, approving a `pending` match has a second side effect beyond marking the cycle Paid: it's what flips `RecurringPayment.is_trusted` from `false` to `true` (see below) — the very first approval is what unlocks future auto-apply for that payment.

## Lifecycle: RecurringPayment.is_trusted (added 2026-08-08 — Epic 8)

```
false --[first RecurringPaymentMatch approved for this payment]--> true
```

- One-way, per-payment. Never reverts to `false` — there's no requirement or story asking for "un-trusting" a payment; if a trusted payment's matches start drifting outside tolerance, FR-7 already routes those individual matches back to `pending` review without touching the trust flag itself.
- Trust never transfers between payments (US-8.5's explicit edge case) — it's a column on the specific `RecurringPayment` row, not a global setting.

## Lifecycle: Transaction.embedding_status (added 2026-08-11 — Local Embedding-Based Semantic Similarity, Epic 9)

```
pending --[Embedding Manager successfully computes + persists the embedding]--> completed
```

- One-way, two-state, per BR-24. No `failed` state — a transient failure just leaves the row `pending` for the next poll cycle (FR-10).
- Every `Transaction` row starts `pending` — both newly-ingested rows (the default) and every pre-existing row (via the migration that adds this column, FR-11). This single default is what unifies forward processing and the one-time historical backfill into one mechanism: the Embedding Manager's poll-cycle handler doesn't need to know or care whether a `pending` row is old or new.

## Lifecycle: RecurringPayment.embedding_status (added 2026-08-12, retroactively during Ingestion Worker Service Functional Design — Local Embedding-Based Semantic Similarity, Epic 9)

```
(created, or name updated) --[API Service write]--> pending --[Embedding Manager successfully computes + persists the embedding]--> completed
                                     ^                                                                                                 |
                                     +-------------------------------- name updated again -------------------------------------------+
```

- Two write paths, per BR-25: API Service (Recurring Payments Component) sets `pending` on create or on any `name`-changing update; Ingestion Worker Service (Embedding Manager Component) is the only writer of `completed`, exactly as for `Transaction.embedding_status`.
- Unlike `Transaction.embedding_status`, this field can cycle back to `pending` after having reached `completed` — a rename invalidates the stored embedding, and there's no reason to keep matching against stale text. An update that leaves `name` unchanged does not touch this field.
- Feeds the same `processNextEmbeddingBatch()` poll-cycle handler as `Transaction` rows (Unit 3) — a single mechanism drains both entity types' `pending` backlog, per the Application Design's "one unified mechanism" principle and the Functional Design's Question 1 resolution (Option A).
- Unlike every other lifecycle field on `Transaction` (e.g. `category_source`), this one is purely a processing-status indicator — it carries no semantic claim about the transaction's category, confidence, or whether a similar past transaction exists (FR-7, US-9.1).

## Non-Lifecycle Note: SettingChange (added 2026-08-16 — Configurable Application Settings)

Unlike every entity above, `SettingChange` has no state machine or lifecycle diagram — it carries no `status` field and no row ever transitions between states. Each row is written once, at `updateSetting()` time, and never touched again (BR-28). The only "lifecycle" that exists is at the *collection* level: the table grows by insertion only, one row per successful setting change, read back in `listSettingHistory()` (FR-CAS-9) most-recent-first. This is a deliberate design choice (Application Design's Key Design Resolution 4), not an oversight — an audit-log-shaped entity with a status field to transition would have no meaning here.

## Lifecycle: Account.account_type and type_user_set (added 2026-10-02 — Account Balance at a Point in Time, Epic 13)

`account_type` has three values — `unknown`, `deposit`, `credit_card` — and one flag, `type_user_set`, that decides who may change it:

- **At creation** (by the Account Resolver, from the first statement's extraction): `deposit` or `credit_card` if extraction could tell, otherwise `unknown`. `type_user_set` = false.
- **While `type_user_set` is false**: a later extraction may set or refine the type (for example `unknown` to `deposit`); the precise rule when a later extraction *disagrees* with an earlier known type is Ingestion Worker Functional Design.
- **User correction** (Account Management Component): sets `account_type` to the user's choice and `type_user_set` to true. From then on **no extraction may change the type** (BR-34); only the user can, again.
- **Effect on balances**: only `deposit` accounts take part in balance features (FR-AB-4). `unknown` is treated as non-deposit (A-3), so an account whose type could not be read stays out of every balance and total until the user confirms it.

## Procedure: Account Resolution by Key (added 2026-10-02 — Epic 13)

Run by the Ingestion Worker's Account Resolver for each **account section** of each statement whose extraction **succeeded** (a statement may hold several; two sections that resolve to the same key collapse into one, BR-37). A failed extraction never reaches it, so no account is ever created from one:

1. Build the statement's key: `bank_key` from the extracted bank name; `account_identifier` as printed, normalized only for spacing and hyphens, or none if the statement prints none (A-2); and the statement's currency.
2. Look up an `AccountKey` with that exact (`bank_key`, `account_identifier`, `currency`) (BR-30).
3. **Found**: the statement belongs to that key's account. Nothing else about the account changes except, while `type_user_set` is false, its type (above).
4. **Not found**: create an `Account` (derived name, display `bank_name`, type from extraction or `unknown`, the statement's currency) and its first `AccountKey`, in one step; the statement belongs to the new account.
5. Only one ingestion run is ever active at a time (BR-10), so two statements cannot race to create the same key; BR-30's uniqueness is the backstop if that assumption ever fails.

## Procedure: Account Merge (added 2026-10-02 — Epic 13)

Account A is absorbed into account B, in this order, as one all-or-nothing operation (BR-35):

1. Refuse unless A and B have the same currency (BR-31), **and** no single statement has a section for both (a statement that lists both proves they are different accounts; this also keeps BR-37 safe in step 3).
2. Settle anchors: both have one, the caller must name the survivor and the other is removed; only one has one, it ends up on B; neither has one, nothing to do.
3. Re-point every `StatementAccount` of A to B (revised 2026-10-03).
4. Re-point every `AccountKey` of A to B. This is what makes the merge permanent: a later statement that used to resolve to A now resolves to B through the same key.
5. Delete A, which now has no statement sections, keys, or anchor — the only state in which the schema allows an account to be deleted.

B's own name, type, and `type_user_set` are unchanged. Transactions need no change at all: each belongs to an account only through its statement-account link, and that link moves with the section in step 3.

## Lifecycle: BalanceAnchor (added 2026-10-02 — Epic 13)

- **Absent**: a new deposit account has no anchor and so has no balance ("anchor required", A-8). Captured statement closing balances never stand in for it (they are only the cross-check).
- **Created / replaced**: by the user, for a deposit account only; a replacement overwrites the row in place (BR-32) and every balance for that account immediately reflects it.
- **Inert**: if the account's type stops being `deposit`, the anchor stays but nothing reads it; switching back restores it with no re-entry.
- **Removed**: only as part of a merge (BR-35), when the other account's anchor was chosen to survive.

## Cross-Entity Rule: Closing Balance Capture (added 2026-10-02 — Epic 13)

At ingestion, each account section's printed closing balance and the date it applies to are stored together on that section's `StatementAccount` row (BR-33; moved from `BankStatement` on 2026-10-03, so a multi-account PDF stores one per account) and are never turned into a `Transaction`; the existing rule that balance-restatement lines are excluded from the transaction list is unchanged. Whether a given statement's pair is present depends only on what the statement prints; a missing pair just means that statement has no cross-check. The pair is never edited after being written, other than by a backfill reingest.

## Cross-Entity Rule: Backfill Wipe Order and the Vector-Store Consequence (added 2026-10-02 — Epic 13)

BR-36 fixes *what* the backfill touches; the order matters because of foreign keys. Rows that reference a transaction go first (`recurring_payment_matches`, `categorization_disagreements`, `recategorization_proposals` — which references `recategorization_jobs` as well as a transaction — then `recategorization_jobs`), then `transactions`, then `statement_accounts`, then `bank_statements` (a statement whose PDF is missing from Drive is skipped entirely, BR-36). `ingestion_run_files.bank_statement_id` is set to null before any statement is removed. Reingested transactions start with `embedding_status = pending` (BR-24), so the existing embedding mechanism re-embeds them with no new code.

**Consequence outside the database (not designed here)**: transaction embeddings live in the separate vector store, keyed by transaction id. Deleting transactions here leaves their vectors behind there, pointing at ids that no longer exist, and the vector store client currently has no delete operation. This design cannot fix that; it is handed to the Ingestion Worker's Functional Design (Backfill Tool Component), which must remove those vectors as part of the wipe — otherwise the retroactive re-scan's nearest-neighbor search could return matches that no longer exist. Recurring-payment-name vectors are unaffected, since `recurring_payments` is kept.

## Lifecycle: KnownFile.state (added 2026-10-03 — Probable Duplicate Statement Detection, Epic 14)

```
(no record) --> probable_duplicate --> overridden
(no record) --> confirmed_duplicate --> overridden
```

- **No record to `probable_duplicate`**: inserted by the Probable Duplicate Detector when ingestion skips a file (FR-PD-1), or by the Backfill Tool when it pre-registers the copy it will skip (FR-PD-16). Both carry the matched statement's hash and the comparison (BR-40).
- **No record to `confirmed_duplicate`**: inserted by the Statement Removal Handler when a removal completes, carrying the kept copy's hash and the pair's comparison, so the removed copy's Drive file is never re-ingested (FR-PD-13).
- **To `overridden`**: set by the Duplicate Review Component when the user chooses "Not a duplicate — ingest it" (FR-PD-7), from either earlier state; `decided_at` is stamped. The file is ingested on the **next** run (A-PD-4). The row stays, so the file is never flagged again and the comparison can say it was ingested at the user's request. From a `confirmed_duplicate` this is the in-app way back after a removal; the corrections that sat on the removed copy are not restored.
- No other change is allowed (BR-41). In particular a `probable_duplicate` is **never re-evaluated** by a later run: the record is of a past comparison, and only the user's override changes it. That is what makes the backfill's pre-registered skips independent of the order Drive lists files.

## Lifecycle: DuplicatePair.status (added 2026-10-03 — Epic 14)

```
pending --> dismissed
        --> removed
        --> superseded
```

- **pending**: found by the scan, awaiting the user (FR-PD-9). Its proposal and comparison are refreshed by a later scan. The nav badge counts pending pairs that have no active removal job. *(Added 2026-10-04, Epic 14 Ingestion Worker Functional Design Q1 = C)*: a pending pair with `removal_allowed = false` is listed for information only and stays pending, and counted by the badge, until the user dismisses it.
- **dismissed**: the user said "not a duplicate" (FR-PD-10, A-PD-5). Final: never offered again, and excluded from detection at ingestion and from the backfill's pre-registration.
- **removed**: the database deletion for its removal job committed. Final. (A job that only failed leaves the pair `pending`, so it can be retried.) *(Refined 2026-10-04, Ingestion Worker Functional Design WR-67: originally "a removal job for it completed"; the pair, the removed file's `confirmed_duplicate` record, and the job's move to `embeddings_pending` now commit together with the deletion, because from the user's point of view the statement is gone then, and it stops the file being re-ingested before the embeddings are cleaned. A job that later ends `embeddings_failed` leaves the pair `removed`.)*
- **superseded**: the backfill's reingest resolved it, or a scan found that its statements are no longer both held. Final.

No transition skips a state, and none leaves a final state (BR-44).

## Lifecycle: StatementRemovalJob.status (added 2026-10-03 — Epic 14)

```
queued --> running --> embeddings_pending --> completed
                   |                      |
                   |                      +-> embeddings_failed
                   |
                   +-> failed
```

- **queued**: written by the Duplicate Review Component when the user confirms (FR-PD-10), carrying what the user acknowledged.
- **running**: claimed by the Ingestion Worker's Statement Removal Handler. If the worker stops while a job is `running`, the database deletion has not committed (BR-46), so on restart the job is safely marked `failed`, like a stale ingestion run, and the user may retry.
- **embeddings_pending**: the statement, its sections, its transactions, and their dependents are deleted and committed, and `removed_transaction_ids` is recorded, in one transaction (BR-46). The embeddings are being deleted; a failure here is retried, counted in `embedding_attempts`.
- **completed**: the embeddings are gone, the removed copy's `KnownFile` (`confirmed_duplicate`) is recorded, and the pair is `removed`. Terminal.
- **embeddings_failed**: the retries ran out. The data is deleted; only orphaned vectors remain. Terminal and visible to the user, with a reason.
- **failed**: nothing was deleted. Either re-verification refused the job (the statement is gone, or the removal copy now has more manual corrections than the user acknowledged) or the deletion rolled back. Terminal; the pair stays `pending`, so a new job can be requested (BR-45).

## Cross-Entity Rule: What a Removal Deletes, and What Survives It (added 2026-10-03 — Epic 14)

A removal deletes, for the one statement, in this order and in one transaction: `recurring_payment_matches`, `categorization_disagreements`, `recategorization_proposals`, and `recategorization_jobs` referencing its transactions; its `transactions`; its `statement_accounts`; and the `bank_statements` row, which is BR-36's wipe order scoped to one statement (BR-51 is what keeps the two lists identical). `ingestion_run_files.bank_statement_id` referencing it is set to null, so run history survives, as in the backfill. **Nothing the Epic 14 entities hold is touched**, because they refer to statements by hash (BR-50). The `Account`, `AccountKey`, and `BalanceAnchor` rows are kept, so a removal never loses an anchor or an account; an account left with no statements is harmless and is not deleted.

Outside the database (not designed here): the removed transactions' embeddings live in the vector store; BR-46 and the job lifecycle are what make deleting them safe and retryable, executed by the Ingestion Worker (Unit 3).

## Cross-Entity Rule: Backfill and the Probable-Duplicate Entities (added 2026-10-03 — Epic 14)

When the Backfill Tool (BR-36) wipes and recreates every statement: the `KnownFile` rows survive and are matched by content hash; pending pairs whose statements the reingest resolves are marked `superseded` (BR-44); dismissed pairs are honoured, so a statement the user said is not a duplicate is neither pre-registered nor flagged; the comparison a pre-registered `KnownFile` points at is the pair's existing comparison, so the evidence survives the wipe. The Backfill Tool's backup and restore cover all six new tables, because it adds `KnownFile` rows and changes pair statuses and `restore` must revert both.

## Non-Lifecycle Note: DuplicateComparison, DuplicateComparisonRow, DuplicateScanState (added 2026-10-03 — Epic 14)

The comparison and its rows have no lifecycle: they are written once (BR-42). `DuplicateScanState` is a single row updated in place (BR-48) with no state machine; whether a scan is due is derived by comparing its recorded values with the current settings and statements, and that derivation belongs to Ingestion Worker Functional Design.

## Cross-Entity Rule: Statement Processing Idempotency

Given the same PDF bytes (same `pdf_content_hash`), processing MUST be idempotent at the `BankStatement`/`Transaction` level: a second ingestion run encountering that hash creates an `IngestionRunFile` with `outcome = 'skipped_duplicate'` and inserts **zero** new `Transaction` rows (BR-3, FR-3.2). This is the schema-level guarantee that makes FR-1.4/US-1.4 safe to re-trigger repeatedly.

*Addendum (2026-10-02, Epic 13)*: the one-time backfill (BR-36) deliberately defeats this guarantee for exactly the existing statements, by deleting their `BankStatement` rows so the same PDFs read as new. It is the only sanctioned way to do so; nothing in a normal ingestion run can.

*Addendum (2026-10-03, Epic 14)*: this guarantee covers identical **bytes**. The same statement saved as a different file has different bytes and passes it, which is the gap Probable Duplicate Statement Detection closes at the level of extracted transactions (BR-39..BR-52). The two mechanisms are independent: the exact-bytes check runs first and is unchanged (NFR-PD-6).
