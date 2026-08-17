# Model Training (Unit 5)

Offline dataset curation + categorization-model fine-tuning for the Bank Transaction Insights App. **Not a docker-compose service** — mlx-tune needs Apple Silicon/Metal, which no container on this Mac can reach, so this unit runs directly on the host. See `aidlc-docs/construction/model-training/` for the full design record.

## Setup

1. Make sure the `database` container is running with the loopback port published (already the default in this repo's `docker-compose.yml`):
   ```bash
   docker compose up -d database
   ```
2. Install dependencies:
   ```bash
   cd model-training
   uv sync
   ```
3. Copy `.env.example` to `.env` and fill in `DB_PASSWORD` (same value as the root `.env`) and `OPENROUTER_API_KEY`.
4. Set up ClearML credentials (one-time, separate from this project's `.env`):
   ```bash
   uv run clearml-init
   ```

## Usage

### 1. Curate a dataset
```bash
uv run python -m model_training.curate --output-dir dataset
```
Prints a summary (train/validation counts, source breakdown, excluded-null-amount count) and writes `dataset/train.jsonl` + `dataset/val.jsonl`.

### 2. Fine-tune
```bash
uv run python -m model_training.train --dataset-dir dataset --steps 200
```
Loads the base model, fine-tunes via LoRA, evaluates against the held-out split (accuracy, confusion matrix, agreement rate vs. the currently-deployed live model), logs everything to ClearML, and saves a LoRA adapter to `output/artifact/`.

**Deploying the result back into the running oMLX server is manual and out of scope for this tool** — see the project's Requirements doc (`aidlc-docs/inception/requirements/categorization-model-finetuning-requirements.md`) for why.

## Running tests
```bash
uv run pytest
```
Covers the parts that are meaningfully unit-testable without a real MLX runtime (dataset curation SQL, prompt rendering, evaluation scoring). The actual fine-tuning/inference calls are verified via a live smoke run, not mocked — see `aidlc-docs/construction/build-and-test/`.
