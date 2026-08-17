# Deployment Architecture — Model Training Unit

Not deployed in the sense the other 4 units are (no container, no `docker-compose.yml` entry). "Deployment" here means: how an operator gets this unit runnable.

```
Operator's Mac (same host running docker-compose)
  |
  |  git clone / already-present repo checkout
  v
model-training/  (own .venv, `uv sync`)
  |
  |  curate.py  -->  127.0.0.1:5433  -->  transactagent-db container (Postgres, read-only queries)
  |  train.py   -->  HuggingFace Hub (base model download, one-time, cached)
  |             -->  ClearML SaaS (run tracking)
  |             -->  host.docker.internal:8000 / oMLX server, same one ingestion-worker
  |                  already talks to for evaluate()'s live-model comparison
  v
Local artifact (LoRA adapter / merged model) on the operator's own filesystem
  -- deployment back into the running oMLX server is manual, out of scope (Resolved Decision 7)
```

## Setup Steps (operator-facing, mirrored into `model-training/README.md` at Code Generation)
1. `docker compose up -d database` (if not already running) — the port-127.0.0.1:5433 mapping (Infrastructure Design decision above) takes effect on next `docker compose up`/recreate of the `database` service.
2. `cd model-training && uv sync`
3. Copy `.env.example` to `.env`, fill in `DB_PASSWORD` (same value as the root `.env`) and ClearML credentials (`clearml.conf` or env vars, per ClearML's own setup docs).
4. `uv run python -m model_training.curate` → produces `train.jsonl`/`val.jsonl`
5. `uv run python -m model_training.train` → fine-tunes, evaluates, saves artifact, logs to ClearML
