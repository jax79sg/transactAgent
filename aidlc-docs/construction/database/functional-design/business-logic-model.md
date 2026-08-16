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
- **completed**: All files in the run had outcome `processed` or `skipped_duplicate` (zero `failed`).
- **completed_with_failures**: At least one file had outcome `failed`, but the run itself finished (NFR-2.2 partial-failure isolation — one bad file does not abort the run).
- **failed**: A run-level failure occurred before any per-file processing could complete (e.g., Drive auth failure per US-1.1 edge case) — distinct from a per-file `failed` outcome.

No transition skips a state (e.g., `queued` never jumps directly to `completed`).

## State Machine: IngestionRunFile.outcome

```
(created when file is listed) --> processed
                               --> skipped_duplicate
                               --> failed
```

Terminal, single-assignment — set once when the Orchestrator finishes handling that file, never revised afterward (a genuinely-changed statement per FR-3.2's edge case is a **new** `IngestionRunFile`/`BankStatement` row, not a mutation of the old one).

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

## Cross-Entity Rule: Statement Processing Idempotency

Given the same PDF bytes (same `pdf_content_hash`), processing MUST be idempotent at the `BankStatement`/`Transaction` level: a second ingestion run encountering that hash creates an `IngestionRunFile` with `outcome = 'skipped_duplicate'` and inserts **zero** new `Transaction` rows (BR-3, FR-3.2). This is the schema-level guarantee that makes FR-1.4/US-1.4 safe to re-trigger repeatedly.
