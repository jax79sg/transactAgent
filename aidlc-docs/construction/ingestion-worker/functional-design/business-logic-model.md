# Business Logic Model — Unit 3: Ingestion Worker Service

Technology-agnostic pipeline logic for the 6 components. Final provider/algorithm decisions from the plan: **Gemini API** (vision/PDF) for extraction, **OpenRouter** free-tier text model for categorization LLM fallback, no cross-provider retry, **rapidfuzz** for similarity matching, statement-printed SGD amount prioritized over **exchangerate.host** fallback, 5s worker polling.

## Ingestion Orchestrator: Run Pipeline

```
poll ingestion_runs for status='queued' (every 5s, Question 6 = A)
  -> claim run (status='running')
  -> Drive Connector.listFolderPdfFiles()
  -> update run.files_found_count
  -> for each file:
       Drive Connector.downloadFile(file)
       Duplicate Detection.computeFileHash(bytes)
       -> [already processed] record IngestionRunFile(outcome='skipped_duplicate', bank_statement_id=<existing>)
       -> [new] Statement Extraction.extract(bytes)
                -> [failure] record IngestionRunFile(outcome='failed', failure_reason, raw_extracted_text)
                -> [success] create BankStatement row
                             for each raw transaction:
                               Categorization Engine.categorize(description, context)
                               Currency Conversion.resolveConvertedAmount(transaction, statement_context)
                               persist Transaction
                             Duplicate Detection.recordProcessed(hash, driveFileId)
                             record IngestionRunFile(outcome='processed', transactions_extracted_count)
       update run progress counters after each file (near-live status per US-1.2)
  -> set run.status = 'completed' | 'completed_with_failures' (NFR-2.2: one file's failure never aborts the run)
```

## Drive Connector Component

- **Authenticate**: on first use, complete interactive OAuth (Question 2=A from Requirements Analysis); store refresh token securely (encrypted at rest is out of scope per opted-out Security extension, but the token itself is treated as a secret per NFR-4.1 and never logged).
- **Reauth handling**: if a Drive API call fails with an auth error, mark the run `failed` (run-level, not per-file) with a reason indicating reconnection is needed (US-1.1 edge case) — this is a run-level failure since no files can be processed at all, distinct from a per-file `failed` outcome.
- **List/download**: list PDF files in the configured folder only (FR-1.3); download raw bytes per file.
- **Addendum (2026-08-08, Nightly Transaction Backup, Epic 7)**: 4 new methods, all scoped to the separate, dedicated backup Drive folder (never the ingestion source folder):
  - `ensureBackupFolderExists(parentFolderId)`: query Drive for a child folder named `backup` under `parentFolderId`; create it if not found; return its folder ID. Idempotent — safe to call on every backup attempt.
  - `uploadFile(folderId, filename, bytes, mimeType)`: standard Drive file create/upload call, same OAuth credential and retry/transient-error handling as the existing list/download methods.
  - `listBackupFolderFiles(folderId)`: same pagination pattern as `listFolderPdfFiles`, but queries `folderId` (the `backup` subfolder) with no MIME-type filter (backup files are CSV, not PDF) and returns `createdTime` in addition to id/name, for retention's most-recent-7 sort.
  - `deleteFile(driveFileRef)`: standard Drive file delete call.
  - Reauth handling is identical to the existing pattern: a Drive-API auth failure on any of these 4 methods is classified `drive_connectivity` by the Backup Manager (WR-15), not treated as a run-level ingestion failure — backups and ingestion runs are entirely independent attempts.

## Statement Extraction Component

- **Approach** (Question 2 = A): convert each PDF page to an image and send directly to Gemini with a structured-extraction prompt (schema: bank name, currency, per-transaction date/description/amount/direction, plus an optional printed-SGD-converted-amount field per transaction if visible, plus a statement-level and per-transaction confidence score per Question 4 = B).
- **Structural validation**: the LLM's response MUST parse against the expected JSON schema; a schema-validation failure is an immediate extraction failure (Question 4 = A part).
- **Confidence check** (Question 4 = B): if the LLM's self-reported statement-level confidence is below a threshold (e.g., "low" or a numeric score below a configured cutoff), OR zero transactions were extracted from a statement that isn't genuinely empty, the statement is flagged `failed` with a reason capturing why (schema failure vs. low confidence).
- **No cross-provider fallback** (Clarification 1b = B): if the Gemini call itself errors (timeout, rate limit, API error), the statement is immediately flagged `failed` with that reason — no retry against a different provider.
- **Bank/currency identification**: extracted directly from the LLM's structured response (it's asked to identify the bank name and primary currency as part of the same call).

## Categorization Engine Component

- **Fallback chain** (FR-5.2, unchanged from Application Design, now with concrete algorithms):
  1. **Similarity Matcher**: fuzzy-match (rapidfuzz token-sort ratio, Question 3 = A) the new description against past transaction descriptions, restricted to transactions with `category_source IN ('manual', 'similarity', 'llm')` (i.e., not `unsure`), ranking `manual`-sourced matches above others regardless of raw fuzzy score (FR-5.3 precedence) as long as they clear a minimum similarity floor.
  2. **LLM Classifier**: if no match clears the similarity threshold, call the OpenRouter free-tier text model with the whitelist + description, constrained (via structured output / enum constraint) to return one of the whitelist category names or "UNSURE".
  3. If the LLM call itself fails (no cross-provider fallback, Clarification 1b = B) or returns a value outside the whitelist, assign `UNSURE`.
- **Retroactive re-scan** (FR-5.4, RecategorizationJob handler): given a manually-corrected `source_transaction`, re-run the Similarity Matcher (step 1 only — no LLM call needed, since this only ever looks for existing precedent) against all current `UNSURE` transactions; any that now clear the threshold against this specific corrected transaction are updated to the corrected category with `category_source = 'similarity'`... **Note**: this is a slight refinement worth flagging — retroactively-updated transactions get `category_source = 'similarity'` (not `'manual'`), since the correction is applied algorithmically, not by direct user action on that specific transaction; this preserves the meaning of `manual` as "a human directly edited this exact row."
- **Addendum (2026-08-08, Epic 8 — Recurring Payments)**: The similarity matcher gains a second, independent caller — Recurring Payment Manager's `matchNewTransaction` (WR-16) — matching a transaction's description against a `RecurringPayment`'s name instead of against past transaction descriptions. No change to the matcher's own internals; this is purely a new call site, confirmed at Functional Design per NFR-1.
- **Addendum (2026-08-11 — Similarity-Matching Normalization fix, WR-20)**: `find_best_match` now normalizes both the incoming description and every candidate's description through a new `normalize_reference_noise` function immediately before computing `token_sort_ratio` — strips reference-code-shaped noise (digit runs of 3+, short letter+digit tokens like a QR code fragment) so a repeat payment to the same payee isn't blocked from matching purely by a unique per-transaction reference code embedded in the text. Applies identically to both of the matcher's callers (the retroactive re-scan above, and Epic 8's `matchNewTransaction`) since both flow through the same `find_best_match`. The amount-range gate (`amounts_in_range`) runs independently, before text scoring, and is unaffected. Forward-only — no retroactive re-scan of historical transactions is triggered by this fix itself (FR-6); existing precedent/re-scan mechanisms simply benefit the next time they run.
- **Addendum (2026-08-12 — Local Embedding-Based Semantic Similarity, Epic 9, WR-21..25)**: Both `findSimilarPastTransaction` and `findRecategorizationCandidates` now try embedding-based search first, `find_best_match` becoming the fallback rather than the first attempt:
  ```
  findSimilarPastTransaction(description):
    query_vector = Embedding Manager.computeEmbedding(description)         [raw text, WR-24]
    if query_vector succeeded:
      neighbors = Vector Store Client.queryNearestNeighbors(
                    query_vector, collection='transactions', topK=K)        [WR-22]
      for each neighbor in neighbors (nearest first):                      [WR-23]
        candidate = fetch Transaction row by neighbor.entityId
        if candidate clears embedding-similarity threshold
           AND amounts_in_range(transaction, candidate)
           AND (manual-source precedence already satisfied, WR-3):
          return candidate                                                 [used exactly as a fuzzy match would be]
    # embedding unavailable, or no neighbor survived the checks above
    return find_best_match(description, candidate_pool)                   [WR-20 normalization applies here, unchanged]
  ```
  `findRecategorizationCandidates` follows the identical chain per bucket (`UNSURE`, already-categorized), adding `excludeEntityId=<source_transaction_id>` to the nearest-neighbor query (WR-21) since the source transaction may itself already be a stored candidate. No change to WR-9/WR-10's scoring-bucket/auto-apply-threshold logic once a candidate is found — only how the candidate is found.
- **Addendum (2026-08-02, Epic 6 — Recategorization Review Panel, WR-9/WR-10)**: The re-scan above is broadened and split:
  1. Run the same Similarity Matcher against the `UNSURE` bucket (unchanged from above) — but now with **two** score checks instead of one: at/above the new, higher auto-apply threshold → apply directly as before; at/above the existing similarity threshold but below the auto-apply threshold → create a `RecategorizationProposal` (`status = 'pending'`, `source_bucket = 'unsure'`) instead of writing to `transactions`.
  2. Additionally run the Similarity Matcher against a second bucket: already-categorized transactions (`category_source != 'unsure'`) whose current category isn't already the one being proposed, excluding the source transaction itself (BR-15, Unit 1). Any match at/above the existing similarity threshold — at *any* score, including a near-perfect one — creates a `RecategorizationProposal` (`status = 'pending'`, `source_bucket = 'categorized'`); this bucket never auto-applies (WR-10).
  3. Every proposal created (either bucket, either outcome) is one row — `status = 'auto_applied'` for the direct-write case, `status = 'pending'` otherwise — giving a complete record of everything the re-scan found, not just what it changed.
  4. The function's return value (transaction IDs actually written to) only reflects step 1's direct-apply outcomes, since that's what `RecategorizationJob.updated_transaction_count` has always meant; pending-proposal counts are queried directly from `recategorization_proposals` by the API Service (Unit 2), not stored redundantly on the job row.

- **Addendum (2026-08-16 — Matching Precision Refinement, WR-27..32)**: The fallback chain (FR-5.2) is refined. The LLM Classifier is no longer step 2, called only when step 1 fails — it now always runs, once per file, upfront, for every raw transaction (`classifyBatch`, WR-27), before this component's own per-transaction `categorize()` call even begins:
  ```
  # Ingestion Orchestrator, once per file, right after extraction succeeds:
  llm_category_by_description = Categorization Engine.classifyBatch(
      [t.description for t in file.raw_transactions], whitelist)   [WR-27: deduped, concurrent, bounded]

  # then, per transaction, as before:
  categorize(description, amount, llm_category_by_description[description]):
    similarity_match = findSimilarPastTransaction(description, amount, llm_category)   [WR-21 chain, now
                                                                                          price-bucketed
                                                                                          text (WR-29) +
                                                                                          agreement boost
                                                                                          (WR-30)]
    if similarity_match found AND llm_category is a real category:
      if similarity_match.category == llm_category:
        return {category: similarity_match.category, source: 'similarity'}          [agree]
      else:
        recordDisagreement(similarity_match.category, llm_category, similarity_match.score)  [WR-28]
        return {category: UNSURE, source: 'unsure'}                                  [disagreement]
    elif similarity_match found:
      return {category: similarity_match.category, source: 'similarity'}            [LLM abstained]
    elif llm_category is a real category:
      return {category: llm_category, source: 'llm'}                                [similarity found nothing]
    else:
      return {category: UNSURE, source: 'unsure'}                                    [both abstained]
    # llm_category is ALWAYS persisted to the new transaction's llm_suggested_category_id
    # (null if UNSURE), regardless of which branch above fired -- WR-28
  ```
  `recategorizeUnsureFromPrecedent`'s pairwise embedding check also gains price-bucketed text (WR-29) and an LLM-agreement boost (WR-30), but does **not** gain disagreement detection or a `CategorizationDisagreement`-writing branch — that decision (WR-28) is scoped to `categorize()`'s ingestion-time call only, since the retroactive re-scan has no analogous "two independently-computed suggestions for the same not-yet-decided transaction" shape (it's propagating one already-decided correction to other transactions, not deciding a fresh one).

- **Addendum (2026-08-17 — Categorization Model Fine-Tuning, FR-CFT-9, WR-34)**: `classifyBatch`'s LLM prompt gains a second per-item field, `amountSgd` (the transaction's `converted_amount_sgd`), alongside `description`:
  ```
  # Ingestion Orchestrator, once per file, right after extraction succeeds:
  llm_category_by_description = Categorization Engine.classifyBatch(
      [{description: t.description, amountSgd: t.converted_amount_sgd} for t in file.raw_transactions],
      whitelist)   [WR-34: amountSgd added to the prompt, keyed by description as before]
  ```
  This exists solely so the live prompt's input shape matches what the new Model Training unit's Dataset Curator produces (Requirements' Resolved Decision 6) — the fine-tuned model is trained on `{description, amountSgd} -> category`, so inference has to offer the same shape or the fine-tune wouldn't transfer. No change to the fallback chain, the whitelist constraint, disagreement detection, or any other part of `categorize()`'s decision logic above — this is purely a prompt-content change. Bank name is deliberately excluded (Requirements' Resolved Decision 5 — "a very weak signal").

  **Correction found at Code Generation**: `amountSgd` is not actually available at `classifyBatch`'s original call time — Currency Conversion previously ran later, per-transaction, inside the persistence loop. The Ingestion Orchestrator's pipeline was restructured so conversion resolves upfront, per transaction, before `classifyBatch` (same conversion logic/DB effects, just reordered), and the already-computed result is reused rather than recomputed during persistence.

## Currency Conversion Component

- **Primary source** (Clarification 2a = A): if the Statement Extraction step captured a printed SGD-converted amount for a transaction (common on Singapore bank/card statements per user's domain knowledge), use it directly as `converted_amount_sgd`; `conversion_is_approximate = false`, `fx_rate_used_id = NULL` (no API rate was used — the source was the statement itself, not a cached rate).
- **Fallback source**: if no printed SGD amount was captured (or the transaction's original currency is already SGD, in which case `converted_amount_sgd = amount` trivially with no lookup needed), fetch/cache a historical rate from **exchangerate.host** (Clarification 2b = B) for the transaction's date; if the exact date is unavailable, use the nearest prior date and set `conversion_is_approximate = true` (FR-10.5).
- **Total unavailability**: if neither a printed amount nor any FX rate (even historical fallback) can be obtained, set `conversion_unavailable = true`, leave `converted_amount_sgd = NULL` (FR-10.5).
- **Caching**: fetched rates are cached in `fx_rate_cache` keyed by (currency pair, date) so repeated lookups for the same date don't re-call the API (FR-10.4) — this cache is only populated by the fallback path, since statement-printed amounts never touch the FX API at all.

## Duplicate Detection Component

- Unchanged from Application Design: hash raw PDF bytes, check against `bank_statements.pdf_content_hash`, record on success.

## Backup Manager Component (added 2026-08-08 — Nightly Transaction Backup, Epic 7)

Checked as the third, lowest-priority branch of `poll_once()` (`services.md` addendum) — only when no ingestion run or recategorization job was found that cycle:

```
isBackupDueNow():
  today = current server/container date
  return (current time >= configured schedule time)
     AND (no BackupRun row exists where backup_date = today)   [WR-11]

runBackup():                                                    [WR-12: must never raise]
  backup_date = today
  started_at = now
  try:
    transactions = query all Transaction rows                  [WR-13, full snapshot]
    csv_bytes = build CSV (all columns, header row)
    folder_id = Drive Connector.ensureBackupFolderExists(dedicated_backup_folder_id)
    filename = f"transactions-backup-{timestamp}.csv"
    Drive Connector.uploadFile(folder_id, filename, csv_bytes, "text/csv")
    enforceRetention(folder_id)
    write BackupRun(backup_date, started_at, completed_at=now,
                     outcome=success, transaction_count=len(transactions),
                     backup_filename=filename)
  except (DriveNotConnectedError, DriveReauthRequiredError, TransientError, HttpError) as e:
    write BackupRun(backup_date, started_at, completed_at=now,
                     outcome=failed, failure_category=drive_connectivity)   [WR-15]
  except Exception:
    write BackupRun(backup_date, started_at, completed_at=now,
                     outcome=failed, failure_category=other)                [WR-15]

enforceRetention(folder_id):                                     [WR-14, US-7.2]
  files = Drive Connector.listBackupFolderFiles(folder_id)
  candidates = files matching this feature's naming convention (transactions-backup-*.csv)
  sort candidates by createdTime descending
  for each file beyond the 7 most recent: Drive Connector.deleteFile(file)
```

Note that `enforceRetention` only runs after a successful upload — a failed attempt (e.g. Drive not connected before any file could be listed) leaves the existing backup set untouched, since there's nothing new to make room for.

## Recurring Payment Manager Component (added 2026-08-08 — Recurring Payments, Epic 8)

Two entry points, with different triggers (`services.md` addendum):

```
matchNewTransaction(transaction):                                [WR-16, called from _persist_transaction()]
  candidates = RecurringPayments with no live match for the relevant cycle
               AND due-date window covers transaction.transaction_date
               AND (description, category) clears the similarity threshold
                   against the payment's name (Categorization Engine's matcher, reused)
  for each candidate:
    cycle_period = derive from the nearer due-date instance                [WR-17]
    if candidate.is_trusted AND amount is within tolerance of expected:     [WR-18]
      create RecurringPaymentMatch(status=auto_applied, cycle_period, ...)
      # cycle marked Paid immediately, no review needed
    else:
      create RecurringPaymentMatch(status=pending, cycle_period, ...)
      # applies whether never-trusted (always pending, FR-6) or trusted-but-drifted (FR-7)

isDetectionScanDueNow() -> boolean                                [same due-check shape as Backup Manager's isBackupDueNow()]

runDetectionScan():                                                [WR-19]
  group recent transactions by normalized description/category + similar amount
  keep groups with >= 2 occurrences, ~30 days apart (monthly-cadence only, FR-12)
  for each qualifying group not already covered by a RecurringPayment's matches
      and not already represented by a DetectionSuggestion row (BR-22 backstop):
    create DetectionSuggestion(description_pattern, suggested_amount,
                                suggested_category_id, occurrence_count, status=new)
```

Approving a `pending` match (API Service, Recurring Payments Component) is what sets the owning `RecurringPayment.is_trusted = true` — the Worker only ever reads `is_trusted` in `matchNewTransaction`'s tolerance check (WR-18); it never sets it itself. This mirrors the existing API-writes/Worker-reads split already used for `RecategorizationProposal` resolution in Epic 6.

**Addendum (2026-08-12 — Local Embedding-Based Semantic Similarity, Epic 9, WR-21..23)**: The description/category similarity check inside both entry points now tries embedding-based search first:

```
matchNewTransaction(transaction):
  query_vector = Embedding Manager.computeEmbedding(transaction.description)   [raw text, WR-24]
  candidates = []
  if query_vector succeeded:
    neighbors = Vector Store Client.queryNearestNeighbors(
                  query_vector, collection='recurring_payment_names', topK=K)   [WR-22: RecurringPayment.name target]
    candidates = [RecurringPayment rows for neighbors clearing the embedding threshold, nearest first]  [WR-23]
  if candidates is empty:
    candidates = find_best_match(transaction.description, active RecurringPayment names)  [WR-20 fallback, unchanged]
  # from here, WR-16's existing due-date-window + no-live-match filtering applies to `candidates` exactly as before
  ...

runDetectionScan():                                                      [WR-22, corrected 2026-08-13]
  # WR-19's own grouping (exact-normalized-description dict-key matching) is UNCHANGED and stays
  # the primary mechanism -- it never called find_best_match to begin with, so there is no
  # "fuzzy-text search" here for an embedding step to go "before" (unlike the other 3 call sites).
  groups = group recent transactions by normalized description/category + similar amount   [unchanged, WR-19]
  groups = merge_groups_via_embedding(groups):                             [new, purely additive]
    for each pair of distinct group keys:
      vector_a = Embedding Manager.computeEmbedding(most-recent txn in group A)   [transient, WR-24]
      vector_b = Embedding Manager.computeEmbedding(most-recent txn in group B)
      if both succeeded AND cosine_similarity(vector_a, vector_b) >= threshold:
        union(group A, group B)                                           [union-find over group keys]
      # embedding unavailable for either representative -> groups simply stay unmerged
      # (no fuzzy-text fallback for this pass specifically -- WR-19's own grouping already IS
      # the baseline this pass enhances, not something needing a second fallback layer)
  keep groups with >= 2 occurrences, ~30 days apart (monthly-cadence only, FR-12)   [unchanged]
  for each qualifying group not already covered by a RecurringPayment's matches
      and not already represented by a DetectionSuggestion row (BR-22 backstop):  [unchanged --
      # a DB join against RecurringPaymentMatch, not a vector search]
    create DetectionSuggestion(description_pattern, suggested_amount,
                                suggested_category_id, occurrence_count, status=new)
```

No change to WR-16's due-date-window filtering, WR-17's cycle-period derivation, WR-18's trust/tolerance decision, or WR-19's ≥2-occurrences/~30-day cadence criteria — this addendum only changes how a *candidate* is found, matching this component's Epic 8 addendum above ("No logic change to the Categorization Engine itself; this is purely a new call site" — same principle applied here to Epic 9).

**Addendum (2026-08-16 — Matching Precision Refinement, WR-29/30)**: Both entry points' embedded query text now includes the price-range bucket (WR-29), same as the Categorization Engine's. Candidate scoring gains the WR-30 boost:
```
matchNewTransaction(transaction):
  # transaction.llm_suggested_category is already known (set during categorize(), same transaction, WR-28)
  raw_scores = Vector Store Client.queryNearestNeighbors(...)   [entityId -> raw cosine score, unfiltered]
  for each candidate RecurringPayment:
    score = raw_scores.get(candidate.id)
    if score is not None AND candidate.category AND candidate.category.name == transaction.llm_suggested_category:
      score = min(1.0, score + embedding_llm_agreement_boost)                          [WR-30]
    matched = score is not None AND score >= embedding_similarity_threshold
  # unchanged from here: WR-16's due-date-window + no-live-match filtering, WR-18's trust/tolerance decision

runDetectionScan()'s merge_groups_via_embedding:
  for each pair of group representatives A, B:
    score = cosine_similarity(vector_a, vector_b)
    if (A.llm_suggested_category == B.category.name) OR (B.llm_suggested_category == A.category.name):
      score = min(1.0, score + embedding_llm_agreement_boost)                          [WR-30, symmetric]
    if score >= embedding_similarity_threshold: union(A, B)
```
No disagreement-review branch in either entry point (WR-28 is scoped to `categorize()` only) — a candidate that doesn't clear the (possibly boosted) threshold simply isn't matched/merged, exactly as before this feature.

## Vector Store Client Component (added 2026-08-12 — Local Embedding-Based Semantic Similarity, Epic 9)

All interaction with the vector database, mirroring the Drive Connector's "all interaction with Google Drive" role. No business logic of its own beyond the two operations below — every decision about *when* to call it or *what to do* with the result lives in the calling component (Categorization Engine, Recurring Payment Manager, Embedding Manager).

```
upsertEmbedding(collection, entityId, vector):
  write vector into `collection`, keyed by entityId                       [idempotent: same entityId overwrites, WR-26]

queryNearestNeighbors(vector, collection, filters={excludeEntityId}, topK):
  return up to topK (entityId, similarityScore) pairs from `collection`,
  ranked by cosine similarity descending, excluding filters.excludeEntityId if set   [WR-21/WR-22/WR-23]
```

Two logical collections: `transactions` (keyed by `Transaction.id`) and `recurring_payment_names` (keyed by `RecurringPayment.id`) — never mixed in a single query (WR-22). Exact product/index configuration is an NFR Requirements/Infrastructure Design decision (NFR-2), out of scope here.

## Embedding Manager Component (added 2026-08-12 — Local Embedding-Based Semantic Similarity, Epic 9)

Two responsibilities: computing a one-off embedding on demand (used transiently by Categorization Engine and Recurring Payment Manager at query time, WR-21) and owning the async/batched storage-time job (WR-26) — checked as the fifth, lowest-priority branch of `poll_once()` (`services.md` correction), only when nothing else was due that cycle:

```
computeEmbedding(text) -> Vector | EmbeddingUnavailable:                    [WR-24: text passed raw, no WR-20 normalization]
  try:
    return call configured oMLX endpoint with text
  except (ConnectionError, TimeoutError, HttpError):
    return EmbeddingUnavailable                                            [WR-25: never raises]

processNextEmbeddingBatch() -> {processedCount}:                            [WR-26]
  rows = select up to <batch_size> rows, ordered by created_at ASC, id ASC, where:
           (Transaction.embedding_status = 'pending')
        OR (RecurringPayment.embedding_status = 'pending')                  [services.md correction, Database BR-25]
  processedCount = 0
  for each row in rows:
    vector = computeEmbedding(row.description or row.name)
    if vector is EmbeddingUnavailable:
      break                                                                 [stop early this cycle, WR-25/FR-10 — row stays pending]
    Vector Store Client.upsertEmbedding(
      collection = 'transactions' if row is Transaction else 'recurring_payment_names',
      entityId = row.id, vector = vector)
    row.embedding_status = 'completed'                                     [only after the upsert succeeds, WR-26]
    processedCount += 1
  return {processedCount}
```

An interrupted batch (worker restart, endpoint goes down mid-batch) simply leaves the remaining rows `pending` — the next poll cycle's call picks up exactly where the backlog left off, with no separate resume state to track (NFR-4). This single mechanism is "the async embedding job" for new/renamed rows and "the one-time historical backfill" for pre-existing ones (FR-6/FR-11) — there is no code path that distinguishes the two.
