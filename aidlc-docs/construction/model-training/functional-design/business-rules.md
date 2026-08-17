# Business Rules — Model Training Unit

New unit, fresh rule numbering (MTR-1, MTR-2, ...) — not a continuation of any existing unit's numbering.

## MTR-1: Eligibility Query (Dataset Curator, FR-CFT-1)
A transaction is eligible for curation if and only if:
```sql
category_source = 'manual'
OR (
  category_source = 'similarity'
  AND id IN (SELECT candidate_transaction_id FROM recategorization_proposals WHERE status = 'approved')
)
```
`category_source = 'llm'` and `category_source = 'unsure'` are always excluded (Requirements' Resolved Decision 4). The `categorization_disagreements`-resolved-to-similarity path (also identified during Requirements Analysis) contributes **0 rows** against the real live data as of this feature's build (confirmed via direct query — `WHERE status='resolved' AND resolved_category_id=similarity_category_id` currently returns 0 rows) but is still included in the query for correctness, since it's a real, valid signal that will simply start contributing rows once any disagreement gets resolved that way in the future.

## MTR-2: Null-Amount Exclusion (FR-CFT-2, see `domain-entities.md`)
An otherwise-eligible transaction (MTR-1) with `converted_amount_sgd IS NULL` is excluded from the curated dataset entirely — not included with a placeholder value. Counted separately (`excluded_null_amount_count`) so this is visible in the curation summary, not silent.

## MTR-3: No Deduplication
Unlike the live categorization prompt's per-file de-duplication (WR-27 — an API-call efficiency measure, not a data-quality decision), dataset curation does **not** deduplicate by description. A description appearing on multiple eligible transactions (e.g. a recurring monthly charge, each instance separately manually-corrected or approved) contributes one training example per transaction — repeated real-world signal, not redundant noise, for a fine-tuning dataset.

## MTR-4: Deterministic Train/Validation Split (FR-CFT-3, NFR-CFT-4)
Default split ratio 85/15 (train/validation), overridable via CLI argument. The split is **deterministic given the same eligible-row set**: rows are sorted by `transaction_id` (a stable, arbitrary-but-fixed order — not insertion order, which could vary run to run) before splitting, so re-running curation against an unchanged DB state always produces the identical train/validation partition (NFR-CFT-4's reproducibility requirement, applied to the split step specifically, not just the row-selection step).

## MTR-5: Dataset Export Format (FR-CFT-4)
Two JSONL files (`train.jsonl`, `val.jsonl`), one `TrainingExample` (see `domain-entities.md`) per line, each rendered as an SFT-style single-turn chat example so it directly matches mlx-tune's `SFTTrainer` conversational format and, structurally, WR-34's live prompt shape:
```json
{
  "messages": [
    {"role": "user", "content": "Classify this bank transaction description into exactly one of the following categories, responding with ONLY the category name and nothing else:\n\nCategories: <comma-separated active category whitelist>\n\nTransaction description: <description>\nTransaction amount: <amount_sgd> SGD\n\nIf none of the categories clearly fit, respond with exactly: UNSURE"},
    {"role": "assistant", "content": "<category_name>"}
  ],
  "_transaction_id": "<uuid>",
  "_description": "<description>",
  "_amount_sgd": "<amount_sgd as string>"
}
```
Only `messages` is a model input (what `SFTTrainer` trains against). The `_`-prefixed fields are this project's own metadata — `_transaction_id` for traceability (NFR-CFT-4), `_description`/`_amount_sgd` so `evaluate()`'s live-model comparison (MTR-7) can call the live oMLX server with the same raw fields without reverse-parsing them back out of the rendered prompt text.
The user-turn template is intentionally the **same string template** WR-34 uses in `openrouter_client.classify_description` (whitelist substituted with the full active-category list at curation time, not a per-example subset) — this is the whole point of Requirements' Resolved Decision 5/6: training input must match live input exactly, not just approximately.

## MTR-6: LoRA / Training Defaults (FR-CFT-5)
Deferred-to-Code-Generation defaults (CLI-overridable, none hardcoded as the only option):
- LoRA rank: 16, alpha: 16, dropout: 0, bias: none, `finetune_language_layers=True`/`finetune_attention_modules=True`/`finetune_mlp_modules=True`/`finetune_vision_layers=False` (text-only task, no image input ever) — **corrected at Code Generation**: mlx-tune's plain-text quick-start defaults (`target_modules=[...]`) don't apply to Gemma 4, which requires the VLM API path even for text-only fine-tuning (see `business-logic-model.md`'s correction note); the values above instead match mlx-tune's own real, runnable Gemma-4-specific examples (`examples/39_gemma4_text_to_sql.py`, `examples/40_gemma4_moe_finetuning.py`), not the generic README quick start.
- Learning rate: 2e-4, matching the same Gemma-4-specific examples.
- Steps/epochs: not fixed here — genuinely dataset-size-dependent (1,247 rows is small for an LLM fine-tune), left as a required CLI argument rather than a silent default, so a run is never accidentally under- or over-trained by an unexamined default.

## MTR-7: Evaluation — Live-Model Comparison Mechanism (FR-CFT-7b)
**Correction found during Functional Design**: no HTTP endpoint exists anywhere in this codebase for "classify this description on demand" — the existing categorization logic (`ingestion-worker`'s `categorize()`/`classify()`) only ever runs internally, during file ingestion. Application Design's phrasing ("calls the live categorization path") is clarified here rather than requiring a new API surface: `evaluate()` independently constructs the identical prompt WR-34 builds (MTR-5's template) and calls the **same oMLX server** (`OPENROUTER_BASE_URL`/`OPENROUTER_MODEL`, read from local config exactly as Requirements' Resolved Decision 9 already established for DB credentials) directly via its own lightweight OpenAI-compatible HTTP client — not by calling into `api-service` or `ingestion-worker`'s Python code, and not via any new endpoint. This keeps Model Training a true leaf/offline unit (Application Design's stated goal) while still comparing against the real, currently-deployed model's real behavior.

## MTR-8: Accuracy / Confusion Matrix Definition (FR-CFT-7a)
Accuracy: exact string match between the fine-tuned model's predicted category name and the validation example's ground-truth `category_name` (a prediction outside the whitelist, or `UNSURE`, counts as incorrect — it never matches a real category label). Confusion matrix: ground-truth category (rows) × predicted category (columns), including an `UNSURE`/`invalid` column for out-of-whitelist predictions, logged to ClearML as a table/plot (ClearML's native confusion-matrix reporting).

## MTR-9: ClearML Task Identity (FR-CFT-6)
Project name: `transactagent-categorization-finetuning` (fixed, not configurable — a single project keeps every run comparable in one place, matching the whole point of using ClearML). Task name: timestamp-based (`finetune-{ISO8601 run start}`), so successive runs never collide and sort chronologically in the ClearML UI without additional user input.
