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

**Addendum (2026-08-18, Background Process Visibility feature — see `background-process-visibility-application-design-plan.md`)**: The new **Background Activity Component** is a sixth, independent, read-only orchestration point — same shape as Backup Status: a single-method component that only queries the Shared DB (`ingestion_runs`/`recategorization_jobs`), polled frequently by the Frontend (NFR-BPV-1) rather than on-demand like the others. No write path — all writes to those tables happen in the Ingestion Worker Service, as they already do today.

**Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)**: Two new independent orchestration points, the seventh and eighth: the **Account Management Component** (synchronous direct DB writes — rename, merge, correct type, set/replace anchor — the same shape as Recategorization Review's approve/reject and the Configuration Component's `updateSetting`) and the **Balance Component** (synchronous, read-only). Neither involves the Ingestion Worker Service during the request, and neither uses the Run/Job Queue: balances are **computed on request** from accounts, anchors, statements, transactions, and `fx_rate_cache`, with nothing precomputed or stored, because a replaced anchor or an account merge would invalidate any stored result. Discrepancy checks (`listDiscrepancies`) are likewise computed on request, so a corrected anchor clears its warning with no further action (US-13.6). The Balance Component's FX lookup is **cache-only** (Question 1 = A) — it reads `fx_rate_cache` rows the Ingestion Worker already wrote and never calls an external FX service, so this feature adds no new external dependency to API Service. Orchestration for a lookup: (1) resolve the requested date or month; (2) read each deposit account's anchor and net flow; (3) apply the pure `balanceFromAnchor`; (4) convert to SGD via `lookupFxRateAsOf`, marking approximate or unavailable as appropriate; (5) assemble per-account rows, the combined total, and the named exclusions.

**Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)**: One new independent orchestration point, the ninth: the **Duplicate Review Component**. Its dismiss, override, and re-check actions are synchronous direct row writes (the same shape as Recategorization Review's approve/reject). **Confirming a removal** is the one action that does not finish inside the request: it writes a removal job row and returns; the Ingestion Worker executes it (below) and the Frontend polls the pair's status. That split exists because deleting a statement must also delete its embeddings, and the API Service never connects to the vector store.

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

**Addendum (2026-10-02, Account Balance at a Point in Time feature — Epic 13, see `account-balance-application-design-plan.md`)**: The per-file pipeline gains one step: after Statement Extraction succeeds, the **Account Resolver Component** resolves (or creates) the statement's account, and the processed-statement record is then written carrying the account reference and the printed closing balance. A file whose extraction fails never reaches the resolver, so no account is created from a failed extraction. Extraction itself gains three optional statement-level fields; every existing safety net is unchanged (NFR-AB-3). No new `poll_once()` branch, no new poll-loop work: account resolution runs inline within the existing per-file step. *Scope change (2026-10-03)*: a statement can hold several accounts, so that step runs once per account section, and each section's transactions are converted with the section's own currency and linked to the section.

**Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14, see `probable-duplicate-application-design-plan.md`)**: The per-file pipeline gains **two** checks, at two different moments, for two different reasons. The first exists so a file already judged is never read by Gemini again (NFR-PD-2); the second exists so a skipped file creates nothing (FR-PD-1). The Account Balance additions are shown in place so the whole sequence reads in order:

```
Drive Connector.downloadFile
  -> Duplicate Detection.isAlreadyProcessed(hash)?            [exact bytes, unchanged]
       -> [yes] mark file "skipped_duplicate", next file
  -> Duplicate Detection.lookupRememberedFile(hash)           [NEW check 1, always on, before extraction]
       -> probable_duplicate | confirmed_duplicate:
            mark file "skipped_probable_duplicate" (link to its stored comparison), no Gemini call, next file
       -> overridden: continue, exempt from check 2
       -> none: continue
  -> Statement Extraction.parseTransactions
       -> [failure] mark file "failed" with reason, next file
       -> [success]
            if detection is on and the file was not overridden:   [NEW check 2, before anything is created]
              Probable Duplicate Detector.findProbableDuplicateOf(extracted, hash)
                -> [match] recordSkippedDuplicate (comparison + remembered file "probable_duplicate")
                           mark file "skipped_probable_duplicate", next file
            per account section: Account Resolver.resolveAccount ...        [Account Balance, unchanged]
            classifyBatch, convert, persist each transaction, recordProcessed
            mark file "processed"
```

A remembered probable duplicate is a **record of a past comparison and is never re-evaluated**; only the user's override changes it. That is what lets the Backfill Tool pre-register a skip by hash and have the reingest honour it whichever file Drive lists first. If two new files in one run duplicate each other, the first is persisted before the second is judged, so the second is flagged against it (A-PD-7); the per-file SAVEPOINT already makes the first visible to the second.

`poll_once()` gains two branches. Final order (each branch runs only when every branch before it found nothing, the existing one-thing-per-cycle invariant, WR-8/NFR-1; no new locking):

```
poll_once():
  1. queued IngestionRun                                  -> process it; return
  2. queued RecategorizationJob                           -> process it; return
  3. pending statement removal job            [NEW]       -> Statement Removal Handler.processNextRemoval(); return
  4. Backup Manager.isBackupDueNow()                      -> runBackup(); return
  5. Recurring Payment Manager.isDetectionScanDueNow()    -> runDetectionScan(); return
  6. Probable Duplicate Detector.isPairScanDueNow() [NEW] -> runPairScan(); return
  7. embedding backlog                                    -> processNextEmbeddingBatch()
```

Placement is by who is waiting. A removal (3) is a user-requested action with the user watching its status, so it follows the run and job a user can also be waiting on and precedes the housekeeping branches. The pair scan (6) is not time-sensitive, but it must come **before** the embedding backlog (7): that branch has work on every cycle while any embedding is pending, so anything placed after it could starve during the one-time historical backfill. Because branch 3 sits above backup and the scans, a removal that can never finish would starve them; the Statement Removal Handler therefore bounds its retries and parks a job that exhausts them (a Functional Design requirement).

**Removal flow** (the one cross-service flow in this feature):

```
Frontend --confirm--> API: Duplicate Review.confirmRemoval
                        writes a removal job row (carries what the user acknowledged); returns
Worker poll_once branch 3: Statement Removal Handler.processNextRemoval
  1. claim the job; re-verify (target exists; its manual corrections not above the acknowledged count)
       -> [fails] job "failed" with reason; nothing deleted; user may retry
  2. ONE database transaction: delete the statement, its statement-account rows, its transactions
     and every dependent row (shared helper), record the transaction ids on the job; commit
       -> [fails] rolled back; job "failed"; nothing deleted
  3. Vector Store Client.deleteEmbeddings(transaction ids)
       -> [fails] job "embeddings pending"; retried (bounded); only orphaned vectors remain
  4. record the removed file's hash as "confirmed_duplicate"; mark the pair removed; job "done"
API: the panel polls the pair's removal status (pending -> done | failed)
```

**Pair scan**: `Probable Duplicate Detector.runPairScan` applies the same rule as the ingestion check to the stored statements and writes the pairs the Review panel lists. It runs when none has run, when the settings the last scan used have changed, or when a re-check is requested (by the user in the panel, or by the Backfill Tool when it finishes, since new account identifiers can make previously unflaggable small statements flaggable). New duplicates cannot arise through ingestion once detection is on (they are skipped), so the scan finds only statements that were already held. With detection switched off, neither check 2 nor the scan runs; check 1 and the Review panel's handling of pairs already found keep working, because they honour decisions the user has already made.

## Service: Backfill Tool *(new, 2026-10-02, Account Balance at a Point in Time feature — not a docker-compose "service" — see `account-balance-application-design-plan.md`)*

**Responsibility**: The one-time, safety-gated wipe-and-reingest that gives every existing statement an account, an account type, and a closing balance (US-13.7). Documented here alongside the real services for consistency, but like Model Training it has no persistent process, no `poll_once()` participation, no docker-compose entry, no REST endpoints, and no UI (Question 2 = A). It ships in the Ingestion Worker Service's package and image because it needs exactly what that service has: Drive access, the extraction pipeline, and the shared database package.

**Orchestration pattern**: a single manually-invoked command that runs these steps in order, stopping at the first failed gate:

1. **Dry run**: report what would be affected (statements, transactions, manual corrections, dependent rows); change nothing.
2. **Verified backup**: take and verify a backup of the affected data; report its location; refuse to continue if verification fails (NFR-AB-2).
3. **Typed confirmation**: nothing is wiped without an explicit confirmation from the operator.
4. **Capture** manual category corrections, keyed by statement content hash, transaction date, amount, and description.
5. **Wipe** statements, their account sections (`statement_accounts`), transactions, and the rows that depend on them.
6. **Reingest** every Drive PDF by creating an ordinary ingestion run record and driving it through the existing `processRun` in-process, so each statement follows the identical per-file path (including account resolution) and the run appears in the existing run history.
7. **Re-apply** captured corrections best-effort; report each unmatched one individually.
8. **Completion report**: unmatched corrections, failed PDFs with reasons, recurring-payment matches re-derived, dependent row kinds discarded.

**Constraints handed to Functional Design** (see `components.md`'s Backfill Tool Component): the tool must not interleave with the worker's own poll loop (one run is processed at a time today), and the pre-wipe backup mechanism is open — the existing nightly backup covers only the `transactions` table as CSV in Drive, and the worker image has neither `pg_dump` nor a host-mounted output directory — so Functional Design may need to reopen Infrastructure Design, which the execution plan skipped on the condition that no new runtime path was needed.

**Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)**: The Backfill Tool's step list changes in three places. **Dry run** (step 1) also lists the probable-duplicate pairs it will skip and the copy it keeps. **Between capture and reingest** (steps 4–6) it pre-registers each pair's copy-to-skip as a remembered probable duplicate by content hash, so the reingest, which is an ordinary run through `processRun`, skips those files at check 1 with no Gemini call. **Re-apply** (step 7) carries corrections captured from any file skipped as a probable duplicate during the reingest onto the kept copy before reporting any as unmatched, and the **completion report** (step 8) lists the skipped duplicates and the corrections carried. It also gains a read-only `check-duplicates` command alongside `check-extraction`. This feature is built and in place before the backfill is run (FR-PD-18); the tool refuses to start while a removal job or pair scan is pending, as it already does for runs and jobs.

## Cross-Service Coordination: The Run/Job Queue

Because the two services are separately deployable (Question 1 = B) but must coordinate asynchronously (Question 2 = A), a **Run/Job record** in the shared database is the coordination mechanism — chosen over a message broker to keep the docker-compose stack simple (final tech choice — DB-polling vs. a lightweight broker like Redis — is confirmed in NFR Requirements):

1. API Service inserts a run/job row with status `queued`
2. Ingestion Worker Service polls for `queued` rows, claims one (status -> `running`), and processes it via the Orchestrator, updating progress fields as it goes
3. API Service's `getRunStatus`/`getRunHistory` methods simply read the same row(s) — no direct service-to-service call is needed for status reporting
4. On completion, Worker sets status to `completed` or `completed_with_failures`

This keeps the two services decoupled: the API Service never blocks on or directly calls the Worker Service, and the Worker Service never needs to know anything about HTTP/the Frontend.

*Addendum (2026-10-03, Probable Duplicate Statement Detection feature)*: a **statement removal job** is a third kind of queued row in the same mechanism (alongside ingestion runs and recategorization jobs): the API Service inserts it as requested, the Ingestion Worker claims and executes it, and the API Service reads its status from the same row. No new coordination mechanism. Likewise the user's **override** and **dismissal** decisions and a **re-check** request are plain rows the worker reads on its next cycle or next run.

## Cross-Service Coordination: Settings Override File *(added 2026-08-16, Configurable Application Settings feature)*

A second, genuinely new coordination mechanism, alongside the Run/Job Queue above — not a replacement for it, and not used for anything the Run/Job Queue already handles. Forced by a real constraint (Key Design Resolution 3, `configurable-app-settings-application-design-plan.md`): both services' `Settings` objects are constructed once at process start, before any DB connection exists (their own fields include the DB connection parameters) — so a DB-backed override mechanism has a chicken-and-egg problem a file doesn't.

1. API Service's Configuration Component validates and writes a changed setting's new value to a shared, non-secret override-settings file (on a new Docker volume bind-mounted into both containers — exact path is Infrastructure Design's job).
2. Nothing happens automatically. The Account Owner runs the manual restart command `getRestartGuidance()` gave them (Resolved Decision 2 — no automation, no Docker socket, anywhere).
3. On its next start, the restarted container's `Settings` class reads the override file via pydantic's `env_file` support, alongside its normal process-environment values.

Not a "direct call" in the sense the Run/Job Queue section's rule means: no RPC, no synchronous request/response, no availability coupling between the two services at write time. One side writes a file; the other passively reads it, independently, whenever it next starts. Busy/idle status (FR-CAS-7) is deliberately **not** part of this channel — see Key Design Resolution 2: it's answered by a Shared DB query instead, keeping the original "coordinate only through the DB" rule fully intact for that piece.

## Service: Model Training *(new, 2026-08-17, Categorization Model Fine-Tuning feature — not a docker-compose "service" — see `categorization-model-finetuning-application-design-plan.md`)*

**Responsibility**: Curate a fine-tuning dataset from labeled transactions and fine-tune the categorization model. Documented here alongside the two real services for consistency, but architecturally different in a way worth being explicit about: no persistent process, no `poll_once()` loop, no Run/Job Queue participation, no docker-compose entry.

**Orchestration pattern**: Two independent, manually-invoked CLI scripts, run in sequence by the person operating it — not by each other:

```
$ python -m model_training.curate   # Dataset Curator Component.curateDataset()
$ python -m model_training.train    # Fine-Tuning Trainer Component.train() -> evaluate() -> saveArtifact()
```

`curate` must complete before `train` runs (the latter reads the former's output directory) — a filesystem hand-off, not a DB or queue-mediated one like the two real services use with each other. Neither script talks to the API Service or Ingestion Worker Service directly; `train`'s `evaluate()` step calls the live categorization path only to compare predictions (read-only, no state change), the same way any other client of that functionality would.

## Data Flow Summary

```
Frontend --REST--> API Service --reads/writes--> Shared DB <--reads/writes-- Ingestion Worker Service --calls--> Google Drive API, LLM API, FX Rate API, OCR
```

*Addendum (2026-10-02, Account Balance at a Point in Time feature)*: no new edges. The new Account Management and Balance Components talk only to the Shared DB (the Balance Component reads `fx_rate_cache` rather than calling the FX Rate API, per Question 1 = A), and the new Account Resolver Component talks only to the Shared DB. The Backfill Tool is a command-line entry point inside the Ingestion Worker Service's image, so it adds no edge of its own: it uses the same Shared DB and Google Drive API connections that service already has.

*Addendum (2026-10-03, Probable Duplicate Statement Detection feature)*: no new edges. The new Duplicate Review Component talks only to the Shared DB; the new Probable Duplicate Detector and Statement Removal Handler talk to the Shared DB, and the Removal Handler additionally to the existing Vector Store Client (the Ingestion Worker's existing edge to the Vector DB). Nothing new reaches Google Drive, the LLM, or oMLX: a skipped file is judged from the transactions Gemini already extracted, and a file recognized by its content hash is not extracted at all.
