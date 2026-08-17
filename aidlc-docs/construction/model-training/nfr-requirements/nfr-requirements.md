# NFR Requirements — Model Training Unit

## Platform Constraint (drives most decisions below)
mlx-tune is Apple-Silicon/MLX-only — it has no CUDA path and, more importantly, no Docker path either: Docker Desktop on macOS runs Linux containers inside a VM with no Metal/GPU passthrough, so mlx-tune cannot run inside a container on this host regardless of image choice. This independently confirms Requirements' Resolved Decision 9 (host-run, no `Dockerfile`) was the only workable choice, not just a preference.

## Availability / Reliability
- No uptime requirement — this is a manually-triggered, one-shot CLI tool, not a running service (NFR-CFT-5). "Reliability" here means: a failed run (network blip to HuggingFace/ClearML, DB connection drop) fails loudly with a clear error and a non-zero exit code — never a silent partial dataset or a silently-abandoned training run. No retry/backoff machinery is introduced (unlike `ingestion-worker`'s `retry_with_backoff`) — an operator re-runs the script by hand; this isn't an unattended background process where automatic retry matters.

## Performance
- No throughput/latency SLA. Dataset curation against ~1,247 rows is expected to complete in low single-digit seconds (one SQL query + one JSONL write). Training run duration is inherently variable (dataset size × steps × hardware) and explicitly not bounded by any requirement.

## Security
- Read-only DB credentials: reuses the existing `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` env vars already used by the other 4 units (same `.env`, consistent with this project's existing single-source-of-config convention) — no new credential set introduced for the DB connection itself. NFR-CFT-2 (read-only) is enforced at the query level (SELECT-only statements, no ORM write calls anywhere in this unit's code), not via a separate DB role — a dedicated read-only Postgres role was considered and rejected as unnecessary ceremony for a single-operator local tool with no untrusted input path (Requirements never asked for one, and this project has no existing precedent for per-unit DB roles).
- ClearML credentials (NFR-CFT-3): supplied via ClearML's own standard mechanism (`clearml.conf` in the user's home directory, or `CLEARML_API_ACCESS_KEY`/`CLEARML_API_SECRET_KEY` env vars) — never committed, never read from this project's `.env`. `model-training/.env.example` documents this expectation without containing real values, matching every other unit's `.env.example` convention.
- oMLX server access (`evaluate()`, MTR-7): reuses `OPENROUTER_BASE_URL`/`OPENROUTER_MODEL`/`OPENROUTER_API_KEY` — read from the same `.env` the other units already use for this. No new secret.

## Maintainability / Testability
- Dataset Curator's SQL/eligibility logic (MTR-1/2/3/4) is fully unit-testable against a real Postgres test database, same `testcontainers` pattern the other 3 backend units already use (NFR-CFT-6).
- The Fine-Tuning Trainer's `train()`/`evaluate()` are **not** meaningfully unit-testable in the traditional sense — they depend on a real MLX runtime, a real (large) model download, and a real oMLX server. Coverage strategy: pure/deterministic pieces (prompt-template construction reused from MTR-5, JSONL parsing, accuracy/confusion-matrix computation given already-known predictions) are extracted into small, independently-testable functions; the actual `mlx_tune.FastLanguageModel`/`SFTTrainer` calls and the live HTTP evaluation calls are integration-level, verified via a real smoke run at Build and Test, not mocked unit tests pretending to cover ML training correctness.

## Tech Stack Selection
See `tech-stack-decisions.md`.
