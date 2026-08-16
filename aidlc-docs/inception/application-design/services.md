# Services — Bank Transaction Insights App

Per Question 1 (separate services) and Question 2 (async background job), there are two deployable services plus the orchestration patterns inside each.

## Service: API Service

**Responsibility**: The only service the Frontend talks to. Owns request/response concerns: auth, transaction CRUD/filter/group, dashboard queries, config, and the trigger/status side of ingestion. Never performs OCR, LLM calls, or Drive I/O itself.

**Orchestration pattern**: Thin orchestration — each component above is largely self-contained; the one cross-component orchestration is `Transaction Management Component.correctCategory()` calling `Ingestion Trigger & Status Component.enqueueRecategorizeJob()` after a manual correction, to hand off retroactive re-categorization to the Worker Service (since categorization logic lives there — see Application Design Plan answer analysis).

**Addendum (2026-08-02, Recategorization Review Panel feature)**: The new **Recategorization Review Component** is a second, independent orchestration point within API Service — it does not sit in the `correctCategory()` call chain above. Its approve/reject actions are synchronous, direct DB writes (analogous to `correctCategory()` itself), not routed through the job queue. Only *proposal generation* stays async, on the existing Worker-side path — the human review step is a separate, synchronous concern layered on top of that async output. See `recategorization-review-application-design-plan.md` for why this split was made rather than asked.

**Addendum (2026-08-08, Nightly Transaction Backup feature)**: The new **Backup Status Component** is a third, independent, read-only orchestration point — a single-method component that only queries `backup_runs`. No write path exists in API Service for backups; all backup writes happen in the Ingestion Worker Service.

**Addendum (2026-08-08, Recurring Payments feature — Epic 8)**: The new **Recurring Payments Component** is a fourth, independent orchestration point. Register CRUD and match/suggestion *resolution* (approve/reject/dismiss/add-from-suggestion) are synchronous, direct DB writes from API Service — same precedent as Recategorization Review's approve/reject. Match/suggestion *creation* (deciding a transaction matches something, or that a pattern looks like an untracked subscription) stays exclusively on the Ingestion Worker Service side, via the mechanisms described in the Ingestion Worker Service section below — API Service never performs matching or detection itself.

**Addendum (2026-08-16, Configurable Application Settings feature — see `configurable-app-settings-application-design-plan.md`)**: The extended **Configuration Component**'s `updateSetting()` is a fifth, independent orchestration point, with a strictly-ordered internal flow (no step runs if an earlier one fails):

```
updateSetting(name, newValue):
  1. look up name on the static allow-list -> NotFoundError if absent (covers every excluded secret, by construction)
  2. validate newValue against the setting's real type/range -> ValidationError if invalid; nothing written
  3. write newValue to the shared override-settings file (never root .env)
  4. record a SettingChange history row (previous value, new value, timestamp)
  5. return getRestartGuidance(name) — owning service, exact command, busy/idle (Ingestion-Worker-owned settings only)
```

Steps 3-5 are synchronous, direct writes/reads within the same request (same precedent as Recategorization Review/Recurring Payments' approve/reject) — no job queue involved, since nothing here requires the Ingestion Worker Service to do anything *during* the request; it only ever reads the resulting file later, on its own restart.

## Service: Ingestion Worker Service

**Responsibility**: All heavy/slow/external-integration work: Drive access, OCR, LLM-assisted extraction, categorization, FX conversion, and persisting the results. Runs asynchronously relative to any user-facing request (Question 2 = A).

**Orchestration pattern**: The **Ingestion Orchestrator Component** is the single coordination point. It polls (or is notified of) queued run/job records and, for an ingestion run, executes this pipeline per file:

```
Drive Connector.downloadFile
  -> Duplicate Detection.isAlreadyProcessed?
       -> [yes] mark file "skipped", continue to next file
       -> [no]  Statement Extraction.parseTransactions
                  -> [failure] mark file "failed" with reason, continue to next file (NFR-2.2 partial-failure isolation)
                  -> [success] for each raw transaction:
                       Categorization Engine.categorize
                       Currency Conversion.convert
                       persist Transaction
                     Duplicate Detection.recordProcessed
                     mark file "processed"
  -> update run-level progress after each file
```

**Addendum (2026-08-16, Matching Precision Refinement feature, see `matching-precision-refinement-application-design-plan.md`)**: The per-file pipeline gains a new upfront step, right after `Statement Extraction.parseTransactions` succeeds and before the existing per-transaction loop:

```
[success] Categorization Engine.classifyBatch(all raw transactions' descriptions, whitelist) -> llmCategoryByDescription
          for each raw transaction:
            Categorization Engine.categorize(description, context, llmCategoryByDescription[description])
            Currency Conversion.convert
            persist Transaction
          Duplicate Detection.recordProcessed
          mark file "processed"
```

`classifyBatch` fires its underlying LLM calls concurrently (FR-MPR-3), so this step's wall-clock cost is roughly one round-trip, not one per transaction. The rest of the per-transaction loop is otherwise unchanged — `categorize()` now just takes the already-known classification as a parameter instead of computing it internally as a last resort (Key Design Resolution 2).

For a retroactive re-categorization job (triggered by the API Service after a manual correction), the Orchestrator instead calls `Categorization Engine.recategorizeUnsureFromPrecedent()` directly (no Drive/Extraction steps involved). **Addendum (2026-08-02)**: this method now writes some results directly (high-confidence `UNSURE` matches, US-6.2) and others as pending proposal rows instead (US-6.3) — see `component-methods.md` for the exact split. The job's external shape (queued row in → processed row out) is unchanged.

**Addendum (2026-08-08, Nightly Transaction Backup feature)**: `poll_once()` gains a third, lowest-priority branch:

```
poll_once():
  if a queued IngestionRun exists: claim + process it via the Orchestrator; return
  elif a queued RecategorizationJob exists: claim + process it via the Orchestrator; return
  elif Backup Manager.isBackupDueNow(): Backup Manager.runBackup(); return
  else: nothing to do this cycle
```

At most one of {run, job, backup} is ever processed per poll cycle — the existing "one thing at a time" invariant (WR-8/NFR-1) is preserved by simply extending its existing if/elif chain, not by adding new locking. The Backup Manager never runs concurrently with an active run or job, and is only ever checked when the worker would otherwise have been idle that cycle.

**Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9, see `embedding-similarity-application-design-plan.md`)**: Two distinct kinds of embedding computation exist, at two different layers — worth stating up front to avoid confusion with the `poll_once()` branch introduced below:
- **Query-time** (inside `Categorization Engine` and `Recurring Payment Manager`, both addended above): a transient, non-persisted embedding of the description being matched *right now*, computed synchronously as part of the existing call — not a new orchestration hook, since it's just an internal step of methods that already exist.
- **Storage-time** (new): computing and persisting a transaction's *own* embedding (for the badge, and so it becomes a future candidate) is genuinely async/batched (FR-6), and gets its own `poll_once()` branch, the **fifth**, extending the same if/elif chain established by Backup Manager (Epic 7) and Recurring Payment Manager's detection scan (Epic 8):

```
poll_once():
  if a queued IngestionRun exists: claim + process it; return
  elif a queued RecategorizationJob exists: claim + process it; return
  elif Backup Manager.isBackupDueNow(): Backup Manager.runBackup(); return
  elif Recurring Payment Manager.isDetectionScanDueNow(): Recurring Payment Manager.runDetectionScan(); return
  elif any transaction has embedding_status = pending: Embedding Manager.processNextEmbeddingBatch(); return
  else: nothing to do this cycle
```

Placed last (lowest priority) since it's the least time-sensitive of the five — a transaction's badge lagging by a cycle or two (FR-6) is explicitly acceptable, unlike a queued run/job or a due backup. Same one-thing-per-cycle invariant (WR-8/NFR-1), no new locking.

**Correction (2026-08-12, retroactively during Ingestion Worker Service Functional Design — see `ingestion-worker-embedding-similarity-functional-design-plan.md`)**: the fifth branch's due-check above was written as "any transaction has `embedding_status = pending`," but that's now incomplete. `RecurringPayment` rows also carry an `embedding_status` (Database `BR-25`, added retroactively once Functional Design surfaced that nothing else tracks when a `RecurringPayment`'s name embedding needs computing). The corrected condition is: `elif any Transaction OR RecurringPayment row has embedding_status = pending: Embedding Manager.processNextEmbeddingBatch(); return` — still one branch, still lowest priority, `processNextEmbeddingBatch()` itself now drains both entity types' backlogs (see `component-methods.md`'s corresponding addendum).

**Addendum (2026-08-08, Recurring Payments feature — Epic 8)**: Two separate hooks, not one, since matching and detection have fundamentally different triggers:

- **Matching** (US-8.4/8.5) is *transaction-triggered*, not poll-triggered — it runs as an additional step inside `_persist_transaction()` (the same pipeline step in `orchestrator/pipeline.py` that already categorizes and saves each new transaction during an ingestion run), immediately after a transaction is persisted. There is no reason to wait for a separate poll cycle to check something that's already known the instant the transaction exists.
- **Detection** (US-8.6) is *time-triggered*, not transaction-triggered — a periodic "scan history for patterns" job with no natural single moment to run it. `poll_once()` gains a **fourth** branch, checked only when no run, job, or backup was due that cycle — extending the same if/elif chain Backup Manager (Epic 7) already established, preserving the same one-thing-per-cycle invariant with no new locking:

```
poll_once():
  if a queued IngestionRun exists: claim + process it; return
  elif a queued RecategorizationJob exists: claim + process it; return
  elif Backup Manager.isBackupDueNow(): Backup Manager.runBackup(); return
  elif Recurring Payment Manager.isDetectionScanDueNow(): Recurring Payment Manager.runDetectionScan(); return
  else: nothing to do this cycle
```

## Cross-Service Coordination: The Run/Job Queue

Because the two services are separately deployable (Question 1 = B) but must coordinate asynchronously (Question 2 = A), a **Run/Job record** in the shared database is the coordination mechanism — chosen over a message broker to keep the docker-compose stack simple (final tech choice — DB-polling vs. a lightweight broker like Redis — is confirmed in NFR Requirements):

1. API Service inserts a run/job row with status `queued`
2. Ingestion Worker Service polls for `queued` rows, claims one (status -> `running`), and processes it via the Orchestrator, updating progress fields as it goes
3. API Service's `getRunStatus`/`getRunHistory` methods simply read the same row(s) — no direct service-to-service call is needed for status reporting
4. On completion, Worker sets status to `completed` or `completed_with_failures`

This keeps the two services decoupled: the API Service never blocks on or directly calls the Worker Service, and the Worker Service never needs to know anything about HTTP/the Frontend.

## Cross-Service Coordination: Settings Override File *(added 2026-08-16, Configurable Application Settings feature)*

A second, genuinely new coordination mechanism, alongside the Run/Job Queue above — not a replacement for it, and not used for anything the Run/Job Queue already handles. Forced by a real constraint (Key Design Resolution 3, `configurable-app-settings-application-design-plan.md`): both services' `Settings` objects are constructed once at process start, before any DB connection exists (their own fields include the DB connection parameters) — so a DB-backed override mechanism has a chicken-and-egg problem a file doesn't.

1. API Service's Configuration Component validates and writes a changed setting's new value to a shared, non-secret override-settings file (on a new Docker volume bind-mounted into both containers — exact path is Infrastructure Design's job).
2. Nothing happens automatically. The Account Owner runs the manual restart command `getRestartGuidance()` gave them (Resolved Decision 2 — no automation, no Docker socket, anywhere).
3. On its next start, the restarted container's `Settings` class reads the override file via pydantic's `env_file` support, alongside its normal process-environment values.

Not a "direct call" in the sense the Run/Job Queue section's rule means: no RPC, no synchronous request/response, no availability coupling between the two services at write time. One side writes a file; the other passively reads it, independently, whenever it next starts. Busy/idle status (FR-CAS-7) is deliberately **not** part of this channel — see Key Design Resolution 2: it's answered by a Shared DB query instead, keeping the original "coordinate only through the DB" rule fully intact for that piece.

## Data Flow Summary

```
Frontend --REST--> API Service --reads/writes--> Shared DB <--reads/writes-- Ingestion Worker Service --calls--> Google Drive API, LLM API, FX Rate API, OCR
```
