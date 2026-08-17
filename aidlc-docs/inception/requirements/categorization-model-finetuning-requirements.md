# Requirements: Categorization Model Fine-Tuning

## Intent Analysis

- **User request**: "the goal of this feature is to fine tune existing local model to be better at categorising the transactions. this would involve two major aspects. 1: to curate the datasets based on what was labelled so far(except unsure). 2: to create a set of training codes that would use unsloth library to fine tune the local model that's used for categorisation. the training should use ClearML for mlops."
- **Request type**: New Feature — no existing precedent in this project (first ML-training capability; the 4 existing units are all runtime web-application services).
- **Scope estimate**: Cross-system — a new standalone training codebase (reads from the existing database), plus a production code change to `ingestion-worker`'s live categorization prompt (Clarification 2).
- **Complexity estimate**: Complex — new tech stack (MLX-based fine-tuning, ClearML), a hardware/library mismatch discovered and resolved during this phase, and data-quality decisions about what counts as trustworthy ground truth.

## Current Behavior (baseline, confirmed against the live system — see audit.md)

- Categorization LLM: `OPENROUTER_MODEL=gemma-4-26b-a4b-it-4bit`, served at `OPENROUTER_BASE_URL=http://host.docker.internal:8000/v1` — an **oMLX (Apple Silicon / MLX) server** on the same Mac, not a CUDA endpoint. The exact HF source is `mlx-community/gemma-4-26b-a4b-it-4bit` (an MLX-format, 4-bit-quantized checkpoint).
- The live categorization prompt (`ingestion-worker/categorization/llm_classifier.py`'s `classify`/`classify_batch_prompt`) sends only the transaction `description` text plus the whitelist of 54 active category names — no amount, bank, date, or currency.
- `category_source` distribution across the 6142 real transactions: `similarity`=4961, `manual`=537, `llm`=594, `unsure`=50.
- A transaction with `category_source='similarity'` does **not** distinguish between "auto-assigned by the pipeline, never reviewed" and "a human explicitly approved this via the Review page" — both `recategorization/service.py`'s `approve_proposal()` and `resolve_disagreement()` leave `category_source` set to `similarity`/`llm` (never `manual`) even when a human made the call. The only way to recover "human approved" is by joining against the audit trail: `recategorization_proposals.status='approved'` (via `candidate_transaction_id`) or `categorization_disagreements.status='resolved' AND resolved_category_id=similarity_category_id` (via `transaction_id`). Queried live: 710 distinct transactions qualify via the approved-proposal path, 0 via disagreements.
- Unsloth (as literally named in the original request) requires CUDA (bitsandbytes/triton) and has no Apple Silicon support — it cannot run on this Mac, which is also the machine serving the model. This was surfaced as a clarifying question and resolved below.

## Resolved Decisions (from clarifying questions + clarification round)

| # | Decision | Answer |
|---|---|---|
| 1 | Fine-tuning target | The categorization LLM only (`gemma-4-26b-a4b-it-4bit`). The embedding model (`embeddinggemma-300m`) is out of scope. |
| 2 | Training library | **mlx-tune** (`github.com/ARahim3/mlx-tune`), as a full replacement for Unsloth — not a fallback or alternative path. Verified: runs natively on Apple Silicon via MLX (no CUDA needed at all), explicitly supports Gemma 4 26B-A4B MoE fine-tuning, loads `mlx-community/*-4bit` HF repos directly, and mirrors Unsloth's own API (`FastLanguageModel`, `SFTTrainer`, `SFTConfig`). |
| 3 | Base model | `mlx-community/gemma-4-26b-a4b-it-4bit` on HuggingFace, loaded directly by mlx-tune. |
| 4 | Ground-truth selection | `category_source='manual'` (537 rows) **union** `category_source='similarity'` rows that a human approved via the Review page (710 rows, identified via the `recategorization_proposals`/`categorization_disagreements` join described above) — **1,247 rows total**. Raw unreviewed `similarity` rows and `llm`-sourced rows are excluded (the latter to avoid the fine-tuned model training on its own model family's past outputs — circular reinforcement risk). `unsure` (50 rows) is excluded per the original request. |
| 5 | Dataset input fields | `description` + `converted_amount_sgd` (the already-currency-converted SGD amount, not raw amount+currency) → target category name. Bank name explicitly excluded ("a very weak signal"). |
| 6 | Live prompt change (in scope) | The live production categorization prompt SHALL also be updated to include `converted_amount_sgd`, so training-time input and live inference-time input match — otherwise the fine-tuned model would be trained on a different input shape than it sees in production. |
| 7 | Post-training deployment | Out of scope. Deliverable is the training pipeline plus a saved model artifact (LoRA adapter / merged model, via mlx-tune's own save methods) — conversion/deployment to the live oMLX server is manual, done by the user later. |
| 8 | ClearML hosting | Hosted SaaS (`app.clear.ml`) — credentials supplied locally via config/env vars, never committed to the repo. |
| 9 | Code location | A new standalone top-level directory (`model-training/`), with its own Python environment/dependencies, separate from the 4 existing docker-compose services. Reads from the database read-only. |
| 10 | Trigger mechanism | Manual CLI scripts only — no scheduling, no docker-compose service, no in-app UI/API trigger. |
| 11 | Evaluation | Both: (a) held-out accuracy + confusion matrix against the curated validation split, and (b) agreement/disagreement rate versus the current live model's prediction on the same held-out set — both logged to ClearML. |

## Functional Requirements

- **FR-CFT-1**: A dataset curation script SHALL select transactions where `category_source='manual'`, OR (`category_source='similarity'` AND the transaction is referenced by an `approved` `recategorization_proposals` row via `candidate_transaction_id`). All other transactions (raw unreviewed `similarity`, `llm`-sourced, `unsure`) SHALL be excluded.
- **FR-CFT-2**: Each curated example SHALL capture: the transaction's `description`, `converted_amount_sgd`, the target category name (matching the live prompt's whitelist naming exactly), and the source `transaction_id` (for traceability, not used as a model input).
- **FR-CFT-3**: The curated dataset SHALL be split into a training set and a held-out validation set (default ratio configurable; not fixed at requirements level).
- **FR-CFT-4**: The curated dataset SHALL be exported in a format directly usable by mlx-tune's `SFTTrainer` (prompt/completion or chat-template shape, decided at Functional Design).
- **FR-CFT-5**: The training script SHALL use mlx-tune's `FastLanguageModel` to load `mlx-community/gemma-4-26b-a4b-it-4bit`, attach LoRA adapters, and fine-tune via `SFTTrainer` against the curated training split.
- **FR-CFT-6**: Each training run SHALL log to ClearML (hosted `app.clear.ml`): run configuration/hyperparameters, training metrics, and produced artifacts.
- **FR-CFT-7**: After training, an evaluation step SHALL run the fine-tuned model against the held-out validation split and report/log to ClearML: (a) accuracy and a confusion matrix against the ground-truth category, and (b) the agreement/disagreement rate between the fine-tuned model's predictions and the current live model's predictions on the same held-out inputs.
- **FR-CFT-8**: The training script SHALL save the resulting artifact locally (LoRA adapter and/or merged model, via mlx-tune's `save_pretrained`/`save_pretrained_merged`). No automated conversion or deployment to the live oMLX server is performed.
- **FR-CFT-9**: The live `ingestion-worker` categorization prompt (`classify`/`classify_batch_prompt` and their callers) SHALL be updated to include `converted_amount_sgd` alongside `description` in the prompt sent to the LLM, so live inference input matches fine-tuning training input.
- **FR-CFT-10**: Dataset curation and training SHALL each be runnable as a standalone manual CLI script under a new `model-training/` top-level directory. No scheduling, docker-compose service, or in-app trigger is introduced.

## Non-Functional Requirements

- **NFR-CFT-1 (Environment isolation)**: `model-training/` SHALL have its own Python environment/dependency set (mlx-tune, ClearML, etc.), independent of the 4 existing units — these are heavyweight ML dependencies not needed by, and not to be added to, the web stack's environments.
- **NFR-CFT-2 (Read-only DB access)**: Dataset curation SHALL only read from the database — no writes to any existing table. Connection mechanism (reuse of existing env-var-based credentials vs. a dedicated read-only role) is deferred to Functional/NFR Design.
- **NFR-CFT-3 (No secrets committed)**: ClearML credentials SHALL be supplied via local config/env vars only, consistent with the project-wide convention already established in `config.py` (NFR-4.1) — never hardcoded or committed.
- **NFR-CFT-4 (Reproducibility/traceability)**: The dataset curation script SHALL be deterministic and re-runnable against the live DB (same DB state → same output), and SHALL log the exact dataset composition (row counts by source) to ClearML for traceability.
- **NFR-CFT-5 (No impact on production availability)**: Training SHALL run entirely outside `docker-compose` — no impact on `api-service`/`ingestion-worker`/`frontend` uptime. The FR-CFT-9 live-prompt change SHALL go through this project's normal per-unit Construction flow (Functional Design → Code Generation → Build and Test) like any other production change, not be treated as part of the offline training tooling.
- **NFR-CFT-6 (Testability)**: Consistent with this project's established practice (all 4 existing units carry real test suites, verified against live containers), the dataset curation query logic (the manual/human-approved-similarity selection criteria) SHALL have test coverage.

## Deferred to Functional/NFR Design (not requirements-level decisions)

- Exact ClearML project/task naming convention.
- Exact LoRA hyperparameters (rank, alpha, target modules, learning rate, steps/epochs) and train/validation split ratio.
- Exact prompt/chat-template format used for SFT training examples, and the exact textual format of the amount in both the training data and the live prompt (e.g. `"45.20 SGD"` vs. a structured field).
- Exact CLI script names/arguments and the precise DB read-only access mechanism.
- Whether `model-training/` needs its own `requirements.txt`/`pyproject.toml` or reuses `uv` tooling patterns already used elsewhere (e.g. this session's frontend Docker build fallback) — a Units Generation / Application Design question, not Requirements.

## Out of Scope

- Any change to the embedding model (`embeddinggemma-300m`) or the existing similarity-matching pipeline.
- Automated conversion or deployment of the fine-tuned model back into the running oMLX server — the user handles this manually.
- Any in-app UI or API endpoint for triggering dataset curation or training.
- Any automation or scheduling of recurring fine-tuning runs.
- Self-hosted ClearML infrastructure (no new docker-compose service for ClearML).
