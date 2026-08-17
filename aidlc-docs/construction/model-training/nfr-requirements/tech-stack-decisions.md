# Tech Stack Decisions — Model Training Unit

| Concern | Choice | Rationale |
|---|---|---|
| Language/runtime | Python 3.12+ | Matches every other unit in this project — no reason to diverge, and `transactagent-db` (reused for read-only DB access) already requires it |
| Dependency management | `uv` + `pyproject.toml`, own `.venv` | Same tooling as the other 3 Python units (`database`/`api-service`/`ingestion-worker`), but a **separate** environment/manifest — NFR-CFT-1 requires isolation, not a different tool |
| Fine-tuning library | `mlx-tune` | Requirements' Resolved Decision 2 — full replacement for the originally-named Unsloth, verified viable during Requirements Analysis (native Apple Silicon, explicit Gemma-4-26B-A4B support, direct `mlx-community/*-4bit` loading) |
| Experiment tracking | `clearml` (official Python SDK) | Requirements' Resolved Decision 8 — hosted SaaS, standard client |
| oMLX HTTP client (`evaluate()`, MTR-7) | `openai` (OpenAI-compatible client) | Same package `ingestion-worker` already uses for the identical kind of call (`openrouter_client.py`) — no reason to introduce a second HTTP client library for the same OpenAI-compatible protocol |
| DB access | `transactagent-db` (local editable path dependency, same as `api-service`/`ingestion-worker`) + `sqlalchemy` (already a transitive dependency of `transactagent-db`) | Application Design's explicit decision: reuse the existing shared package rather than a new data-access layer |
| Config loading | `pydantic-settings` | Same library the other 3 units already use for env-var-backed settings — consistent pattern, and DB credentials are literally the same env vars |
| Dataset/JSONL handling | Python stdlib `json` (read/write) — no `datasets`/`pandas` dependency for curation itself | Curation only ever writes JSONL; `mlx-tune`'s own `SFTTrainer` (via its `datasets` transitive dependency) is what reads it back during training. No need for Dataset Curator to carry a heavy dependency just to write lines of JSON. |
| Testing | `pytest` + `testcontainers[postgres]` | Same as the other 3 backend units, for the parts of this unit that are meaningfully unit-testable (see `nfr-requirements.md`) |

## Explicitly Not Chosen
- **A new read-only Postgres role/user**: considered, rejected — see `nfr-requirements.md`'s Security section.
- **`pandas`**: not needed anywhere in this unit's actual logic (row-by-row SQL result → JSONL is simpler without it); would be an unused-most-of-the-time dependency in an already-heavy ML environment.
- **A second HTTP client (`httpx`/`requests`) for the oMLX call**: `openai`'s client already covers it, and reusing it keeps this unit's oMLX-calling code structurally recognizable next to `ingestion-worker`'s equivalent, for anyone reading both.
