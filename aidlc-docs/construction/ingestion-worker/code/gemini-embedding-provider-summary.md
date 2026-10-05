# Code Summary — Gemini as an Embedding Provider (2026-10-05)

Requirements and the calibration evidence: `../../../inception/requirements/gemini-embedding-provider-requirements.md`. Plan: `../../plans/gemini-embedding-provider-code-generation-plan.md`.

## What changed
| Where | Change |
|---|---|
| `ingestion_worker/config.py` | `embedding_provider: Literal["local", "gemini"] = "local"`, `gemini_embedding_model = "gemini-embedding-2"`. |
| `ingestion_worker/embedding/client.py` | `_provider()` picks endpoint, key, model, timeout, dimensions and prefix. `gemini`: Google's OpenAI-compatible endpoint, `GEMINI_API_KEY`, `gemini-embedding-2`, `dimensions=embedding_dimensions`, input prefixed `task: classification \| query: `, 15 s timeout, no retry; a vector of the wrong size is unavailable. `local`: unchanged (request is exactly `{model, input}`; an empty endpoint still means off). The prefix is applied inside `compute_embedding`, so stored and query text always match. |
| `api_service/app_settings/catalog.py`, `config.py` | `embedding_provider` (standard, enum, default `local`) and `gemini_embedding_model` (advanced); the `embedding_*` local settings say they apply to `local`; catalog 48 → 50; display mirror. |
| `docker-compose.yml`, `.env.example` | `EMBEDDING_PROVIDER`, `GEMINI_EMBEDDING_MODEL` to both backend containers. |
| `integration-tests/embedding_calibration.py` | The calibration tool. |

## Results
Worker 711 tests (691 + 20), API 373 (363 + 10), `ruff` clean; 13 mutations each caught (the first run of the API ones was invalid because I had briefly broken a test file with a careless `sed`, and was re-run on the corrected file). Live deployment is recorded in the audit log.

## Operator notes
- Cosine scores are not comparable between models: set `embedding_similarity_threshold` and `recategorization_auto_apply_threshold` for the model in use (calibrated: local 0.92 / 97, Gemini 0.94 / 99) and re-run `integration-tests/embedding_calibration.py` if the model changes.
- After a switch, existing transactions are re-embedded by the worker's background batch (50 per cycle); until then matching uses what is already embedded plus fuzzy text. Switching the model re-embeds everything.
- The backfill in progress when this was written ran with embeddings off, so its categories came from the LLM plus fuzzy-text matching; embeddings take effect for transactions ingested afterwards.
- `embedding_dimensions` (768) is also the vector size the collection was created with; changing it needs the collection recreated.
