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

## Lifecycle: BackupRun (added 2026-08-08 — Epic 7)

Unlike `IngestionRun.status` and `RecategorizationJob.status` above, `BackupRun` has no `queued`/`running` interim state and no state machine to diagram:

```
(nothing) --> [backup attempt runs synchronously within one Ingestion Worker poll cycle] --> success | failed
```

- `IngestionRun`/`RecategorizationJob` need an interim status because they coordinate *across* services — the API Service inserts a `queued` row, and the Ingestion Worker Service claims and updates it asynchronously, from a separate process, at a separate time (`services.md`'s Cross-Service Coordination pattern).
- A `BackupRun` attempt has no such handoff: it is entirely synchronous within a single Ingestion Worker poll cycle (Application Design `services.md` addendum — `poll_once()`'s third branch calls `Backup Manager.runBackup()` directly, to completion, before the cycle ends). Nothing else claims it mid-flight, so there is nothing for an interim status to represent.
- The row is therefore written exactly once, already in its terminal state (`success` or `failed`, BR-17/BR-18), at the moment the attempt finishes — not created early and updated later.
- `Backup Status Component.getLatestBackupStatus()` (API Service) simply reads the most recent `BackupRun` row by `backup_date` — there is never a "backup in progress" state for it to observe or display.

## Cross-Entity Rule: Statement Processing Idempotency

Given the same PDF bytes (same `pdf_content_hash`), processing MUST be idempotent at the `BankStatement`/`Transaction` level: a second ingestion run encountering that hash creates an `IngestionRunFile` with `outcome = 'skipped_duplicate'` and inserts **zero** new `Transaction` rows (BR-3, FR-3.2). This is the schema-level guarantee that makes FR-1.4/US-1.4 safe to re-trigger repeatedly.
