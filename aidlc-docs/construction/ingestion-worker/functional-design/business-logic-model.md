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
- **Addendum (2026-08-02, Epic 6 — Recategorization Review Panel, WR-9/WR-10)**: The re-scan above is broadened and split:
  1. Run the same Similarity Matcher against the `UNSURE` bucket (unchanged from above) — but now with **two** score checks instead of one: at/above the new, higher auto-apply threshold → apply directly as before; at/above the existing similarity threshold but below the auto-apply threshold → create a `RecategorizationProposal` (`status = 'pending'`, `source_bucket = 'unsure'`) instead of writing to `transactions`.
  2. Additionally run the Similarity Matcher against a second bucket: already-categorized transactions (`category_source != 'unsure'`) whose current category isn't already the one being proposed, excluding the source transaction itself (BR-15, Unit 1). Any match at/above the existing similarity threshold — at *any* score, including a near-perfect one — creates a `RecategorizationProposal` (`status = 'pending'`, `source_bucket = 'categorized'`); this bucket never auto-applies (WR-10).
  3. Every proposal created (either bucket, either outcome) is one row — `status = 'auto_applied'` for the direct-write case, `status = 'pending'` otherwise — giving a complete record of everything the re-scan found, not just what it changed.
  4. The function's return value (transaction IDs actually written to) only reflects step 1's direct-apply outcomes, since that's what `RecategorizationJob.updated_transaction_count` has always meant; pending-proposal counts are queried directly from `recategorization_proposals` by the API Service (Unit 2), not stored redundantly on the job row.

## Currency Conversion Component

- **Primary source** (Clarification 2a = A): if the Statement Extraction step captured a printed SGD-converted amount for a transaction (common on Singapore bank/card statements per user's domain knowledge), use it directly as `converted_amount_sgd`; `conversion_is_approximate = false`, `fx_rate_used_id = NULL` (no API rate was used — the source was the statement itself, not a cached rate).
- **Fallback source**: if no printed SGD amount was captured (or the transaction's original currency is already SGD, in which case `converted_amount_sgd = amount` trivially with no lookup needed), fetch/cache a historical rate from **exchangerate.host** (Clarification 2b = B) for the transaction's date; if the exact date is unavailable, use the nearest prior date and set `conversion_is_approximate = true` (FR-10.5).
- **Total unavailability**: if neither a printed amount nor any FX rate (even historical fallback) can be obtained, set `conversion_unavailable = true`, leave `converted_amount_sgd = NULL` (FR-10.5).
- **Caching**: fetched rates are cached in `fx_rate_cache` keyed by (currency pair, date) so repeated lookups for the same date don't re-call the API (FR-10.4) — this cache is only populated by the fallback path, since statement-printed amounts never touch the FX API at all.

## Duplicate Detection Component

- Unchanged from Application Design: hash raw PDF bytes, check against `bank_statements.pdf_content_hash`, record on success.
