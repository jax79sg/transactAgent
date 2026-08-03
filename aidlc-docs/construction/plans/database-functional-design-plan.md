# Functional Design Plan — Unit 1: Database

**Input**: `aidlc-docs/inception/application-design/unit-of-work.md` (Unit 1 definition), `unit-of-work-story-map.md` (all stories, since every unit's data passes through this schema)

## Unit Context

Unit 1 is schema/migrations only (no runtime business logic of its own). Its "functional design" is the technology-agnostic **domain model** every other unit relies on: entities, relationships, constraints, and business rules that must hold at the data layer (e.g., a transaction's category must be in the whitelist or `UNSURE`; a processed-statement hash must be unique).

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (denormalization of converted amounts, failed-extraction detail retention, category deletion semantics, monetary precision, ingestion-run/file-level tracking granularity)
- [x] Step 2: Generate `domain-entities.md` — all entities, attributes, relationships (ERD-style) — 8 entities
- [x] Step 3: Generate `business-rules.md` — constraints, validation rules, invariants that must hold at the data layer — 13 rules (BR-1 through BR-13)
- [x] Step 4: Generate `business-logic-model.md` — key data lifecycle/state-transition logic that is schema-relevant (e.g., ingestion run status transitions, category_source transitions)
- [x] Step 5: Cross-check every FR/NFR touching data (FR-2 through FR-10, NFR-2) is represented in the domain model — complete, no gaps

## Clarifying Questions

### Question 1 — Converted Amount Storage
Should the SGD-converted amount (FR-10) be a **stored column** on the transaction (computed once at ingestion/conversion time) or **computed at query time** by joining against the FX-rate cache?

A) **Stored column** — `converted_amount_sgd`, `conversion_is_approximate`, `conversion_unavailable` stored directly on the transaction row at write time. Faster dashboard queries (no join/recompute), and the FR-10.5 "approximate/excluded" flags are naturally per-transaction stored facts anyway.

B) **Computed at query time** — only original amount+currency stored; SGD equivalent is joined/computed live from `fx_rate_cache` whenever read. Avoids ever storing a "stale" conversion, but adds query complexity and repeated computation for dashboards.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 2 — Failed/Needs-Review Statement Detail Retention
Per US-1.5, when a statement fails to parse, you want to see why. How much detail should the schema retain for a failed file?

A) A **short failure reason string** only (e.g., "OCR unreadable", "layout not recognized") stored on the ingestion-run-file record — no raw extracted text retained

B) The failure reason **plus the raw extracted text/OCR output** (for later manual debugging or re-processing), stored alongside the run-file record

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 3 — Category Deletion Semantics
Per US-5.2's edge case (removing a category still in use), how should the schema enforce this?

A) **Hard block via foreign-key/referential constraint** — a category cannot be deleted while any transaction references it; the app must reassign transactions first (simplest, most rigid)

B) **Soft-delete** — categories have an `active` flag; removed categories stay in the table (existing transactions keep referencing them, shown as "inactive category") but can no longer be selected for new/corrected transactions

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 4 — Monetary Value Precision
What precision/type should monetary amounts use?

A) **Fixed-point decimal**, 2 decimal places for major currencies (standard accounting precision) — e.g., `DECIMAL(18,2)`

B) **Fixed-point decimal, 4 decimal places** — extra headroom for FX-converted values and currencies that use more than 2 decimal subunits, avoiding rounding-error accumulation across conversions

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 5 — Ingestion Run Tracking Granularity
US-1.2/US-1.5 need both run-level and per-file progress. Should this be two tables (`ingestion_runs` + `ingestion_run_files`) or one flattened table?

A) **Two tables** — `ingestion_runs` (one row per trigger: status, started_at, counts) and `ingestion_run_files` (one row per PDF processed in that run: file id, outcome, failure reason) — normalized, supports the drill-down UI in US-1.5 cleanly

B) **One table** — a single `ingestion_runs` row holds an embedded/JSON list of per-file outcomes — simpler schema, less relational query flexibility

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
