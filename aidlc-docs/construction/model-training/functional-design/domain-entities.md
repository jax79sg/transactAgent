# Domain Entities — Model Training Unit

No new database entities or schema changes (Requirements' scope: read-only against existing tables). The structures below are in-memory/on-disk data shapes, not persisted rows.

## TrainingExample

Produced by the Dataset Curator, consumed by the Fine-Tuning Trainer. One per eligible transaction (FR-CFT-1/2).

| Field | Type | Notes |
|---|---|---|
| `transaction_id` | UUID (string) | Source transaction — traceability only, not a model input (NFR-CFT-4) |
| `description` | string | `Transaction.description`, verbatim — no normalization (consistent with this project's established WR-24 "raw text" precedent for anything fed to a model) |
| `amount_sgd` | decimal (string) | `Transaction.converted_amount_sgd` — always present for an eligible row (see "Amount Availability" below) |
| `category_name` | string | The target label — `Transaction.category.name` at curation time |

### Amount Availability
A transaction eligible under FR-CFT-1 (`manual` or human-approved `similarity`) can, in principle, have `converted_amount_sgd IS NULL` if its conversion was unavailable (WR-6) — the same situation WR-34 handles at inference time by rendering "unknown". For training data specifically: a row with `amount_sgd = NULL` is **excluded** from the curated dataset (not included with a placeholder) — a genuinely missing amount is rare in practice (conversion is only ever unavailable when no FX rate exists at all) and including a "unknown"-labeled example somewhat undermines the point of the amount signal in the first place. Logged as a separate count in the curation summary (alongside `sourceBreakdown`) so this is visible, not silent.

## DatasetSplit

The Dataset Curator's output: two files (train/validation), each a list of `TrainingExample` rows serialized as JSONL (one JSON object per line — mlx-tune's `SFTTrainer` / the underlying `datasets` library both consume this natively via `load_dataset("json", ...)`, no custom loader needed).

## CurationSummary

Returned by `curateDataset()` (not persisted) — reported to the console and logged to ClearML (FR-CFT-6, NFR-CFT-4):

| Field | Type | Notes |
|---|---|---|
| `train_count` | int | Rows in the training split |
| `val_count` | int | Rows in the validation split |
| `source_breakdown` | `{manual: int, human_approved_similarity: int}` | Per-source counts, before the split (NFR-CFT-4 traceability) |
| `excluded_null_amount_count` | int | Rows dropped per "Amount Availability" above |

## TrainingRunResult

Returned by `train()` (not persisted) — a thin summary; the authoritative record of a run lives in ClearML, not this project's own database (Requirements' Resolved Decision 8 — Model Training has no DB write access at all).

| Field | Type | Notes |
|---|---|---|
| `clearml_task_id` | string | For finding the run in the ClearML UI afterward |
| `artifact_path` | string | Local filesystem path to the saved model (FR-CFT-8) |
| `accuracy` | float | Held-out accuracy (FR-CFT-7a) |
| `agreement_with_live_model` | float | FR-CFT-7b |
