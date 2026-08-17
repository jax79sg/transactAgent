# Logical Components — Model Training Unit

Maps the 2 Application Design components onto concrete Python modules (Code Generation will follow this layout):

```
model-training/
  src/model_training/
    config.py          # Settings (pydantic-settings) -- DB + oMLX env vars, reused from .env
    curate.py           # Dataset Curator: eligibility query, split, JSONL export (CLI entry point)
    repository.py        # Read-only SQL queries against transactagent_db models (MTR-1)
    prompt.py             # Shared prompt-template rendering (MTR-5) -- the SAME template string
                            # ingestion-worker's openrouter_client.py builds, kept here as an
                            # independent copy (Model Training has zero import dependency on
                            # ingestion-worker's package, per Application Design) with a test
                            # asserting the two stay textually identical (see build-and-test plan)
    train.py             # Fine-Tuning Trainer: model load, LoRA, SFTTrainer, ClearML (CLI entry point)
    evaluate.py            # evaluate() -- accuracy/confusion-matrix + oMLX live-model comparison (MTR-7/8)
    oMLX_client.py          # Thin OpenAI-compatible client for the evaluate()-only oMLX calls
  tests/
    test_repository.py       # MTR-1..4, against a real Postgres testcontainer
    test_prompt.py             # MTR-5 template rendering, incl. the cross-check against
                                 # ingestion-worker's actual template string
    test_evaluate.py             # Accuracy/confusion-matrix computation given canned predictions
                                   # (MTR-8) -- no real model/HTTP call
  pyproject.toml
  .env.example
  README.md               # How to run curate.py / train.py -- this project's operator-facing
                            # docs convention (see e.g. root README.md) applied to this unit
```

No `Dockerfile` (NFR Requirements' platform constraint) and no entry in `docker-compose.yml` (Application Design/Units Generation decision).
