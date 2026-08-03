# Services — Bank Transaction Insights App

Per Question 1 (separate services) and Question 2 (async background job), there are two deployable services plus the orchestration patterns inside each.

## Service: API Service

**Responsibility**: The only service the Frontend talks to. Owns request/response concerns: auth, transaction CRUD/filter/group, dashboard queries, config, and the trigger/status side of ingestion. Never performs OCR, LLM calls, or Drive I/O itself.

**Orchestration pattern**: Thin orchestration — each component above is largely self-contained; the one cross-component orchestration is `Transaction Management Component.correctCategory()` calling `Ingestion Trigger & Status Component.enqueueRecategorizeJob()` after a manual correction, to hand off retroactive re-categorization to the Worker Service (since categorization logic lives there — see Application Design Plan answer analysis).

**Addendum (2026-08-02, Recategorization Review Panel feature)**: The new **Recategorization Review Component** is a second, independent orchestration point within API Service — it does not sit in the `correctCategory()` call chain above. Its approve/reject actions are synchronous, direct DB writes (analogous to `correctCategory()` itself), not routed through the job queue. Only *proposal generation* stays async, on the existing Worker-side path — the human review step is a separate, synchronous concern layered on top of that async output. See `recategorization-review-application-design-plan.md` for why this split was made rather than asked.

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

For a retroactive re-categorization job (triggered by the API Service after a manual correction), the Orchestrator instead calls `Categorization Engine.recategorizeUnsureFromPrecedent()` directly (no Drive/Extraction steps involved). **Addendum (2026-08-02)**: this method now writes some results directly (high-confidence `UNSURE` matches, US-6.2) and others as pending proposal rows instead (US-6.3) — see `component-methods.md` for the exact split. The job's external shape (queued row in → processed row out) is unchanged.

## Cross-Service Coordination: The Run/Job Queue

Because the two services are separately deployable (Question 1 = B) but must coordinate asynchronously (Question 2 = A), a **Run/Job record** in the shared database is the coordination mechanism — chosen over a message broker to keep the docker-compose stack simple (final tech choice — DB-polling vs. a lightweight broker like Redis — is confirmed in NFR Requirements):

1. API Service inserts a run/job row with status `queued`
2. Ingestion Worker Service polls for `queued` rows, claims one (status -> `running`), and processes it via the Orchestrator, updating progress fields as it goes
3. API Service's `getRunStatus`/`getRunHistory` methods simply read the same row(s) — no direct service-to-service call is needed for status reporting
4. On completion, Worker sets status to `completed` or `completed_with_failures`

This keeps the two services decoupled: the API Service never blocks on or directly calls the Worker Service, and the Worker Service never needs to know anything about HTTP/the Frontend.

## Data Flow Summary

```
Frontend --REST--> API Service --reads/writes--> Shared DB <--reads/writes-- Ingestion Worker Service --calls--> Google Drive API, LLM API, FX Rate API, OCR
```
