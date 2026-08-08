# Domain Entities (Internal DTOs) — Unit 3: Ingestion Worker Service

No new persisted entities — this unit reads/writes Unit 1's schema. These are internal, transient pipeline data shapes.

**Addendum (2026-08-02, Epic 6)**: `RecategorizationProposal` (Unit 1's schema) is written directly by the broadened re-scan (WR-9/WR-10) via `categorization/repository.py`, the same way the existing re-scan already writes `Transaction` rows directly — no new internal DTO is introduced here, matching the existing pattern of this module not modeling its own transient shape for simple repository writes.

## `RawExtractedStatement`
- `bank_name: str | None`
- `currency: str | None`
- `confidence: "high" | "medium" | "low"` (or numeric — finalized in NFR Design/Code Generation)
- `transactions: list[RawExtractedTransaction]`
- `extraction_error: str | None` (set on schema-validation or LLM-call failure)

## `RawExtractedTransaction`
- `transaction_date: date`
- `description: str`
- `amount: Decimal`
- `direction: "in" | "out"`
- `printed_converted_amount_sgd: Decimal | None` (Clarification 2a — captured when the statement itself shows an SGD equivalent)
- `confidence: "high" | "medium" | "low"`

## `CategorizationResult`
- `category_name: str` (a whitelist name, or the literal "UNSURE")
- `source: "similarity" | "llm" | "unsure"`
- `matched_precedent_transaction_id: UUID | None` (set when `source = "similarity"`, for traceability/debugging)

## `ConversionResult`
- `converted_amount_sgd: Decimal | None`
- `is_approximate: bool`
- `is_unavailable: bool`
- `fx_rate_used_id: UUID | None`
- `source: "statement_printed" | "identity_sgd" | "fx_api_exact" | "fx_api_fallback" | "unavailable"` (internal-only, for logging/debugging — not persisted as a separate DB column; `is_approximate`/`is_unavailable`/`fx_rate_used_id` on the `Transaction` row capture what the API/Frontend need per Unit 1's schema)

## `RunProgressUpdate`
- Internal shape the Orchestrator uses to update `IngestionRun` counters after each file — not a new entity, just a note that these are incremental updates (`files_processed_count += 1`, etc.), not a full row replace, so concurrent reads (Unit 2's status polling) always see monotonically-increasing progress.

**Addendum (2026-08-08, Nightly Transaction Backup, Epic 7)**: No new internal DTO is introduced. The Backup Manager writes directly to Unit 1's `BackupRun` schema, matching this module's existing pattern of not modeling a separate transient shape for a simple repository write (same reasoning already used for `RecategorizationProposal`). The CSV export itself is a direct column-for-column dump of `Transaction` rows (WR-13) — not a transformed/derived shape worth naming as its own DTO.
