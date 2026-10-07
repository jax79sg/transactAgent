# Code Summary — Gemini as a Categorization Provider (2026-10-05)

Requirements: `../../../inception/requirements/gemini-categorization-provider-requirements.md`. Plan: `../../plans/gemini-categorization-provider-code-generation-plan.md`.

## What changed
| Where | Change |
|---|---|
| `ingestion_worker/config.py` | `categorization_provider: Literal["local", "gemini"] = "local"`. Any other value stops startup. |
| `ingestion_worker/clients/openrouter_client.py` | `_provider()` picks endpoint, key and model: `local` → `openrouter_base_url` / `OPENROUTER_API_KEY` / `openrouter_model` (unchanged); `gemini` → `https://generativelanguage.googleapis.com/v1beta/openai/` / `GEMINI_API_KEY` / `gemini_model`. Read fresh on every call. The request itself (prompt, temperature 0, 60 s timeout, retry, UNSURE on failure) is identical for both. |
| `api_service/app_settings/catalog.py`, `config.py` | New standard setting `categorization_provider` (enum, default `local`) with a description of the cost and privacy meaning; the two `openrouter_*` descriptions say they apply to `local`; catalog 47 → 48; display-only mirror. |
| `docker-compose.yml`, `.env.example` | `CATEGORIZATION_PROVIDER` to both backend containers. |

## Results
Worker 691 tests pass (674 + 17), API 363 (354 + 9), `ruff` clean; 11 mutations each caught. Deployment verification is recorded in the audit log.

## Operator notes
- Switch on the Settings page (Matching & Categorization → `categorization_provider`) and restart the worker (`docker restart transactagent-worker`); the override file wins over the deployed value, so the container's `CATEGORIZATION_PROVIDER` variable may still read `local` while `gemini` is in effect.
- The extraction key and model are reused: changing `gemini_model` changes categorisation too (Q4 = A). A model that cannot answer this prompt shape would leave transactions UNSURE.
- The free Gemini tier allows roughly 5–15 requests per minute; a rate-limit reply is retried with backoff, then the transaction is UNSURE (WR-7). The user's key showed no throttling at about 200 requests per minute.
- Not covered: embeddings stay on their own setting (Q2 = A); with no embedding model served, matching falls back to fuzzy text and embeddings stay pending.
