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

### 3. Export a classifier dataset
```bash
uv run python -m model_training.classifier_dataset --qdrant-url http://transactagent-vector-db.orb.local:6333
```
Writes `data/classifier-dataset/clf-<id>/dataset.parquet` and `manifest.json`: **every** transaction with its details, its
stored 768-dimension embedding (read from Qdrant, the same vectors the live similarity search uses) and its category, for
training a classifier on frozen embeddings. Qdrant is not published to the host, so on OrbStack use the `.orb.local` address
above (or set `QDRANT_URL`). The output folder is under the git-ignored `data/`; the tool **refuses** to write anywhere git
would not ignore, because the files are real bank transactions and the repository is public.

```python
import pyarrow.compute as pc
import pyarrow.parquet as pq

table = pq.read_table("data/classifier-dataset/clf-<id>/dataset.parquet")   # or datasets.load_dataset("parquet", data_files=...)
train = table.filter(pc.equal(table["split"], "train"))
```

What to know before training on it (the manifest repeats these with the real numbers):

- **The split is by description, not by row.** The same merchant repeats hundreds of times, so a random row split lets the
  model see copies of every test example and the score mostly measures memorisation. Rows with the same normalised
  description never cross `split` (train/val/test) or `fold` (grouped 5-fold cross-validation). A description repeated 50
  times or more is train-only. Both are a function of the description alone, so adding transactions never moves an old one.
- **`label_source` is not uniform trust.** `manual` = set by a person; `similarity` = copied from a similar earlier transaction
  by the same embedding nearest-neighbour search a classifier would learn, so a model trained on it partly imitates that
  search; `llm` = the language model's choice. Compare results with and without each source.
- **Some categories cannot be measured.** The manifest lists categories absent from validation or test, and those with fewer
  than 3 distinct descriptions (impossible to hold out without leakage); use `fold` for the rest.
- **`label_conflict`** marks descriptions that carry more than one category in the data (e.g. a PayNow payee that is
  sometimes Dining, sometimes Others); the amount and direction, already inside the embedding, are the only way to tell them apart.
- **Do not use `llm_suggested_category` as a feature**; it is the language model's own guess, kept only for comparison.
- The embedding model is *declared* (`--embedding-model`, default `gemini-embedding-2`), not read from Qdrant, which stores no
  model name. Before relying on it after a provider change, re-embed a sample and compare, as the 2026-10-18 export did.

## Running tests
```bash
uv run pytest
```
Covers the parts that are meaningfully unit-testable without a real MLX runtime (dataset curation SQL, prompt rendering, evaluation scoring). The actual fine-tuning/inference calls are verified via a live smoke run, not mocked — see `aidlc-docs/construction/build-and-test/`.
