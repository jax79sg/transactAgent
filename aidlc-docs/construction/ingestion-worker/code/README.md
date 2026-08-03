# Unit 3: Ingestion Worker Service — Package Overview

A headless background worker (no HTTP API) that polls for queued ingestion runs and recategorization jobs, and processes them via Google Drive, Gemini, OpenRouter, and exchangerate.host.

## Running Locally (development)

```bash
cd ingestion-worker
pip install -e ".[test]"
export DB_USER=transactagent_app DB_PASSWORD=changeme DB_HOST=localhost DB_PORT=5432 DB_NAME=transactagent
export GEMINI_API_KEY=... OPENROUTER_API_KEY=...
export GOOGLE_OAUTH_CLIENT_ID=... GOOGLE_OAUTH_CLIENT_SECRET=...
python -m ingestion_worker.main
```

Requires Google Drive to already be connected via Unit 2's `/drive/connect` flow (a row must exist in `oauth_credentials`) before a run can list/download files.

## Running Tests

```bash
pip install -e ".[test]"
pytest
```

Requires Docker (testcontainers spins up a disposable Postgres). All external API calls (Gemini, OpenRouter, Drive, exchangerate.host) are mocked in tests — no real API keys or network access needed to run the suite.

## Structure

```
ingestion-worker/src/ingestion_worker/
  main.py                    # asyncio polling loop entrypoint
  config.py                  # env-sourced settings
  db.py                      # session-per-task-iteration
  heartbeat.py                # liveness file for docker healthcheck
  clients/                    # thin external-API wrappers, retry-with-backoff
    retry.py
    gemini_client.py           # extraction (vision/PDF)
    openrouter_client.py       # categorization fallback
    drive_client.py            # reads oauth_credentials, lists/downloads files
    fx_client.py                # exchangerate.host fallback
  extraction/                  # Statement Extraction component
  categorization/               # Categorization Engine component (similarity + LLM)
  currency/                      # Currency Conversion component
  duplicate_detection/            # hash-based dedup
  orchestrator/                    # Ingestion Orchestrator (pipeline.py) + run/job repository
```
