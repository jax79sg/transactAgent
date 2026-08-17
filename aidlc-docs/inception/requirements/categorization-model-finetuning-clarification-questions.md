# Categorization Model Fine-Tuning — Clarification Questions

Two things from your answers need a quick confirmation before I write up the final requirements.

## Clarification 1: Replacing Unsloth with mlx-tune

You answered Q2 with "Other: Consider https://github.com/ARahim3/mlx-tune instead" in response to the CUDA/Apple-Silicon mismatch. I looked it up to verify it's a real, viable fit rather than taking the suggestion at face value:

- Real, active project: 1,382 stars, Apache-2.0, last pushed 2026-06-23, last updated today.
- Runs natively on Apple Silicon via MLX — **no CUDA/cloud GPU needed at all**, training can run right on this Mac. This makes Q2's original A/B/C options (all about finding separate GPU hardware) moot.
- Its docs explicitly list **"Gemma 4 26B-A4B" MoE fine-tuning as stable-supported** — that's an exact match for your model family.
- It loads models directly from HuggingFace, including `mlx-community/*-4bit` quantized repos — an exact match for the checkpoint you linked in Q3 (`mlx-community/gemma-4-26b-a4b-it-4bit`).
- Deliberately mirrors Unsloth's own API (`FastLanguageModel`, `SFTTrainer`, `SFTConfig` — same method names, same call shape), so the training code ends up structurally very close to what Unsloth-based code would have looked like, just importing from `mlx_tune` instead of `unsloth`.

Given that, my read is: **fully replace Unsloth with mlx-tune** as the fine-tuning library for this feature (not "consider it as an option" — an outright substitution), since it actually runs where you need it to and directly supports your exact model. Confirm?

A) Yes — use mlx-tune as a full replacement for Unsloth throughout this feature

B) No — still want literal Unsloth; I'll figure out a separate CUDA environment myself for the actual training run, code should target real Unsloth's API

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Clarification 2: Prompt enrichment scope (amount + bank name)

You answered Q5 with B — include additional transaction fields (amount, bank name) as training input, beyond the description-only prompt the live system uses today. This has a real consequence worth confirming explicitly: it means the **live production categorization prompt** (`ingestion-worker`'s `llm_classifier.py` / `openrouter_client.py` / `categorization/service.py`) would also need to change to build prompts the same enriched way — otherwise the fine-tuned model would be trained on a different input shape than what it actually sees in production, undermining the whole point of fine-tuning it.

Two sub-questions:

### 2a. Which fields exactly, and is changing the live prompt in scope for this feature?

A) Amount + bank name only (as you named) — update the live prompt-building code in this feature so training and inference match

B) Amount + bank name, plus also currency and/or transaction date — update the live prompt-building code in this feature so training and inference match (please note in Other if you want date/currency included)

C) Keep the enriched fields in the **curated training dataset only** for now (for future use) — but leave the live production prompt as description-only for this feature; the first fine-tuned model would then be trained on a slight mismatch versus live inputs, accepted as a known limitation to revisit later

D) Other (please describe after [Answer]: tag below)

[Answer]: D. Just Amount will do. Bank name is actually a very weak signal.

### 2b. If amount is included as a training input, in what form?

A) Raw numeric amount + currency code (e.g. "45.20 SGD") — as originally recorded

B) The already-converted SGD amount only (`converted_amount_sgd`) — consistent units across all transactions regardless of original currency

C) Other (please describe after [Answer]: tag below)

[Answer]: B
