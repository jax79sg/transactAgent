# Categorization Model Fine-Tuning — Clarifying Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference.

Some context pulled from the live system before writing these, so the options below are grounded in what's actually deployed:
- `category_source` breakdown across the 6142 real transactions: `similarity`=4961, `manual`=537, `llm`=594, `unsure`=50.
- The categorization LLM is configured as `OPENROUTER_MODEL=gemma-4-26b-a4b-it-4bit` served at `OPENROUTER_BASE_URL=http://host.docker.internal:8000/v1` — this is an **oMLX (Apple Silicon / MLX) server**, not a CUDA endpoint.
- The categorization prompt currently sends only the transaction `description` text plus the whitelist of 54 active category names — no amount, bank, or date.
- There's a separate `embeddinggemma-300m` model (also served via the same oMLX host) used for semantic-similarity matching (`similarity` source above) — a distinct model from the categorization LLM.

## Question 1
Which model is the fine-tuning target?

A) The categorization LLM only (`gemma-4-26b-a4b-it-4bit`, the one that produces the `llm` category_source and backs the categorization prompt)

B) The embedding model only (`embeddinggemma-300m`, used for `similarity` matching)

C) Both models

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
**Important hardware constraint**: Unsloth requires an NVIDIA GPU (CUDA + bitsandbytes/triton) — it does not run on Apple Silicon/MLX. This Mac (which is currently serving the model via oMLX) has no CUDA GPU, so the training code cannot execute on this machine. Where will training actually run?

A) A separate machine/cloud GPU instance you already have (this repo should just contain portable training code + a README/requirements — you'll copy it over and run it yourself)

B) You don't have GPU access yet and want recommendations as part of this feature (e.g. a cloud GPU rental option)

C) Not sure yet — just build the training code assuming a generic CUDA environment (e.g. a single A100/4090-class GPU), and defer the "where" decision

D) Other (please describe after [Answer]: tag below)

[Answer]: D. Consider https://github.com/ARahim3/mlx-tune instead

## Question 3
The exact base model checkpoint matters for Unsloth (it needs a specific HuggingFace repo id or GGUF/safetensors source it recognizes). "gemma-4-26b-a4b-it-4bit" doesn't match any published Gemma naming scheme I can find. What's the actual base model?

A) It's a custom/local name for a specific HuggingFace Gemma checkpoint — I'll provide the exact HF repo id (please add it after [Answer]: below)

B) I'm not sure of the exact base checkpoint — pick the closest reasonable open Gemma instruction-tuned model available on HuggingFace and use that as the fine-tuning base

C) It's not actually Gemma-family — different base model (please describe after [Answer]: tag below)

D) Other (please describe after [Answer]: tag below)

[Answer]: A.This is the link to the model https://huggingface.co/mlx-community/gemma-4-26b-a4b-it-4bit 

## Question 4
Ground-truth quality for dataset curation: `similarity`-sourced labels (4961 of 6092 eligible rows, ~81%) were assigned automatically by the existing matching pipeline, not necessarily human-verified. Training on them risks reinforcing whatever mistakes the current system already makes. How should these be handled?

A) Include all non-`unsure` rows (`manual` + `llm` + `similarity`) as ground truth, as literally requested — simplest, largest dataset (6092 rows)

B) Use only `manual` (537 rows) as ground truth — smallest but highest-confidence dataset; slower to grow over time

C) Include `manual` + `similarity`, but weight/upsample `manual` rows more heavily during training; exclude `llm`-sourced rows specifically (since that's the same model family being fine-tuned — training on its own past outputs risks circular reinforcement)

D) Other (please describe after [Answer]: tag below)

[Answer]: C. Include manual and similarity that was approved by human

## Question 5
Dataset input format — should the fine-tuning examples mirror the current live prompt exactly (description text + category whitelist → category name), or include more signal?

A) Match the current live prompt exactly: description + whitelist → category name (keeps the fine-tuned model to a drop-in replacement for the existing prompt contract)

B) Include additional transaction fields as context (e.g. amount, bank name) even though the current prompt doesn't use them — richer signal, but means the live prompt-building code would also need to change to match

C) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 6
After a fine-tuning run completes, how should the resulting model actually get back into production use behind `OPENROUTER_BASE_URL`?

A) Out of scope for this feature — deliverable is the training pipeline + a saved model artifact (LoRA adapter or merged weights) only; you'll handle conversion to MLX / deployment to the oMLX server yourself

B) In scope — the training code should also produce something ready to serve (e.g. merged + quantized weights in a format oMLX can load), though the actual "point the server at it" step is still manual

C) In scope, fully automated — training code should also handle conversion and updating the oMLX server's model, end-to-end

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 7
ClearML setup — where should experiment tracking data go, and how should credentials be supplied?

A) ClearML's free hosted SaaS (app.clear.ml) — you already have (or will create) an account; credentials supplied via a `clearml.conf`/env vars you'll fill in yourself, not committed

B) A self-hosted ClearML server (e.g. via docker-compose, similar to how this project already runs Postgres/Qdrant) — should be added as new infrastructure in this repo

C) Not sure yet / open to a recommendation

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 8
Where should this new training code live, and how should it relate to the existing 4 units (Database, API Service, Ingestion Worker Service, Frontend SPA)?

A) A new standalone top-level directory (e.g. `model-training/`) with its own Python environment/dependencies (Unsloth, ClearML, etc.) — separate from the 4 existing docker-compose services, run manually/offline, only reading from the DB (read-only access, e.g. via a DB export step or direct read-only query)

B) A new unit added to `docker-compose.yml` like the other 4 services — always-available as a container, even though it wouldn't run continuously (only triggered manually)

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 9
How should this feature be triggered/run in practice?

A) One-off manual CLI script(s) — you run dataset curation, then training, by hand whenever you want a new fine-tuning pass; no scheduling built in

B) Same as A, but also wire it into the app somewhere (e.g. a button/endpoint) as a future enhancement — for now still manual CLI is fine, just want the design to not preclude it

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 10
Evaluation — how should "the fine-tuned model is actually better" be measured before you'd trust it?

A) Held-out accuracy on a split of the curated dataset (e.g. 85/15 train/val) — compare the fine-tuned model's predicted category vs. the label, report accuracy/confusion matrix via ClearML

B) A/B comparison against the current live model's predictions on the same held-out set (not just raw accuracy, but agreement/disagreement rate with the current model)

C) Both A and B

D) No formal evaluation needed for this feature — just produce the training pipeline; you'll judge quality yourself later

E) Other (please describe after [Answer]: tag below)

[Answer]: C
