# Business Rules — Unit 3: Ingestion Worker Service

## WR-1: Extraction Failure Criteria
A statement MUST be flagged `failed` (not committed) if ANY of: (a) the extraction LLM call errors out (no cross-provider retry, Clarification 1b); (b) the response fails structural/schema validation; (c) zero transactions are extracted from a non-trivially-short statement; (d) the LLM's self-reported confidence is below the configured threshold. **Traces to**: FR-2.5, US-1.3 edge case.

## WR-2: Bank/Currency Must Be Identified to Commit
A statement's extracted transactions MUST NOT be committed unless the extraction step identified both a bank name and a currency for the statement; failure to identify either is treated as an extraction failure (WR-1c, structural incompleteness). **Traces to**: FR-2.3, FR-2.4.

## WR-3: Similarity Threshold and Manual Precedence
A similarity match is only used as precedent if it clears a minimum fuzzy-match score (a configured threshold, tuned during Code Generation/testing — not hardcoded to an arbitrary number here). Among matches clearing the threshold, any `category_source='manual'` match is preferred over `similarity`/`llm`-sourced matches regardless of relative fuzzy score (FR-5.3). **Traces to**: FR-5.2 step 1, FR-5.3.

## WR-4: LLM Categorization Constrained to Whitelist
The categorization LLM call MUST be constrained (structured output / enum) to return only a whitelist category name or the literal "UNSURE"; any other value, or a call failure, results in `UNSURE` being assigned — never a free-text or invalid category value reaching the database (which BR-1 in Unit 1 would reject anyway, but this rule ensures it's handled gracefully at this layer rather than crashing the pipeline). **Traces to**: FR-5.1, FR-5.2 step 4.

## WR-5: Retroactive Recategorization Uses Similarity Only
The FR-5.4 retroactive re-scan (triggered by a manual correction) MUST only use the Similarity Matcher against the newly-corrected transaction — it MUST NOT make an LLM call. Updated transactions get `category_source = 'similarity'`, not `'manual'` (see business-logic-model.md note). **Traces to**: FR-5.4.

## WR-6: Currency Conversion Source Priority
For each transaction, the converted SGD amount MUST be resolved in this order: (1) statement-printed SGD amount if the extraction step captured one, (2) the transaction's own amount if `currency = 'SGD'` already (trivial identity, no lookup), (3) a cached or freshly-fetched `exchangerate.host` historical rate for the transaction's date, (4) the nearest prior date's rate (marked approximate) if the exact date is unavailable, (5) `conversion_unavailable = true` if none of the above succeed. **Traces to**: FR-10.3, FR-10.5, Clarification 2a/2b.

## WR-7: No Silent Retry Across Providers
Neither the extraction (Gemini) nor categorization (OpenRouter) LLM calls retry against a different provider on failure (Clarification 1b = B) — a failure at either step is terminal for that statement/transaction within the current run, surfaced via WR-1 (extraction) or WR-4 (categorization) rather than silently attempted elsewhere.

## WR-8: Single Active Run Respected at the Worker Level Too
Although AR-6 (Unit 2) already prevents a second run from being *enqueued* while one is active, the Ingestion Orchestrator MUST also never concurrently process two runs itself (its polling loop claims and fully completes one run before polling for the next) — a defense-in-depth measure, not a duplicate of AR-6.

## WR-9: Recategorization Search Is Broadened, Still Similarity-Only (added 2026-08-02 — Epic 6)
The retroactive re-scan (FR-5.4, WR-5) is broadened to search two candidate buckets against the corrected transaction — `UNSURE` transactions (as before) and already-categorized transactions (`category_source IN ('manual', 'similarity', 'llm')`) whose current category differs from the correction. WR-5's constraint still holds for both buckets: similarity matching only, no LLM call. A match is split into two outcomes by score: `UNSURE`-bucket matches at or above a new, higher **auto-apply threshold** are applied immediately exactly as WR-5 already specified (`category_source = 'similarity'`); every other match — `UNSURE`-bucket matches at or above the existing similarity threshold (WR-3) but below the auto-apply threshold, and *all* already-categorized-bucket matches regardless of score — creates a `RecategorizationProposal` row with `status = 'pending'` instead of writing to `transactions`. **Traces to**: FR-RR-1, FR-RR-2, FR-RR-3, US-6.1, US-6.2.

## WR-10: Already-Categorized Matches Never Auto-Apply (added 2026-08-02 — Epic 6)
A match against an already-categorized transaction (the bucket added by WR-9) is recorded as a `pending` proposal regardless of how high its similarity score is — the auto-apply threshold in WR-9 applies only to the `UNSURE` bucket. A candidate already assigned the exact category being proposed is skipped entirely (not proposed against itself, a no-op change). **Traces to**: FR-RR-4, US-6.3.

## WR-11: Backup Due Determination (added 2026-08-08 — Epic 7)
A backup attempt is due when both are true: (a) the current time is at or past today's configured nightly schedule time, and (b) no `BackupRun` row exists yet for today's calendar date. This single check, evaluated on every poll cycle, is both the normal nightly trigger and the FR-8 catch-up trigger — a worker that was offline at the scheduled time satisfies condition (a) as soon as it's back online, with no separate startup/catch-up code path needed. **Traces to**: FR-1, FR-2, FR-8.

## WR-12: Every Attempt Records Exactly One Outcome (added 2026-08-08 — Epic 7)
`runBackup()` MUST catch every exception internally and MUST always write exactly one `BackupRun` row (BR-17, Unit 1) before returning — no exception may propagate out uncaught. This is the actual enforcement mechanism for FR-9's no-same-night-retry rule: without a written row, WR-11's due-check would keep returning true on every subsequent poll cycle for the rest of the day, causing a silent retry storm. **Traces to**: FR-9.

## WR-13: CSV Snapshot Content (added 2026-08-08 — Epic 7)
Each backup attempt exports a full snapshot of every row currently in `transactions`, with all columns as stored (per FR-6's documented assumption: raw columns/foreign-key IDs, not human-readable joins) — never an incremental/delta export. **Traces to**: FR-1, FR-6.

## WR-14: Backup Folder Resolution and Retention Scope (added 2026-08-08 — Epic 7)
Backup uploads and retention operate exclusively within the `backup` subfolder of the dedicated backup Drive folder (a separate config value from the ingestion source folder, per FR-3/FR-4) — never the ingestion source folder itself. The subfolder is created if it doesn't already exist (idempotent check, every attempt). Retention (`enforceRetention`) only ever considers files whose name matches this feature's own naming convention (`transactions-backup-*.csv`) — a file that doesn't match is never a deletion candidate, even if it's the oldest file present (NFR-4). **Traces to**: FR-3, FR-4, FR-7, NFR-4.

## WR-15: Failure Classification (added 2026-08-08 — Epic 7)
A failed attempt's `failure_category` is `drive_connectivity` if the failure originated from `DriveNotConnectedError`, `DriveReauthRequiredError`, or a Drive-API `TransientError`/`HttpError` raised by any of `ensureBackupFolderExists`/`uploadFile`/`listBackupFolderFiles`/`deleteFile`; every other exception (e.g. a database error while querying transactions for the export) is classified `other`. **Traces to**: FR-10, FR-11.
