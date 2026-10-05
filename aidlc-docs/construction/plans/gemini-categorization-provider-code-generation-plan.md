# Code Generation Plan — Gemini Categorization Provider (2026-10-05)

**Requirements**: `inception/requirements/gemini-categorization-provider-requirements.md`. **Units**: Ingestion Worker, API Service (catalog + display mirror), deployment files. Frontend unchanged (enumerated settings already render as a dropdown, Epic 14). **Branch**: `feature/account-balance` (PR #25). **Approval**: "Ok go ahead." (2026-10-05).

## Steps
1. [x] Record the accepted answers Q2–Q6 in `gemini-categorization-provider-questions.md`.
2. [x] **Worker config** — `categorization_provider: Literal["local", "gemini"] = "local"` in `config.py` (FR-GC-1, FR-GC-4).
3. [x] **Worker client** — `openrouter_client.py`: `_provider()` returns the endpoint, key and model for the active provider; `_client()`, both request functions and the error messages use it; an explicit `model=` argument still wins (FR-GC-2, FR-GC-3).
4. [x] **API** — catalog entry `categorization_provider` (standard, enum, default `local`), the `openrouter_base_url` / `openrouter_model` descriptions say they apply to `local`, the display-only mirror field, catalog size 47 → 48 (FR-GC-1, FR-GC-5).
5. [x] **Deployment** — `CATEGORIZATION_PROVIDER` passed to both containers in `docker-compose.yml`, documented in `.env.example`.
6. [x] **Tests** — worker: 17 new (`test_openrouter_client.py`, `test_config.py`); API: 9 new and the two count assertions (`test_settings_validation.py`, `test_api_settings.py`).
7. [x] **Verification** — worker 691 pass, API 363 pass, `ruff` clean in both; mutation check: 11 deliberate defects (provider ignored; wrong key, model or endpoint for gemini; error naming the wrong endpoint; explicit model ignored; timeout dropped; value not validated; either default flipped; catalog accepting another value), each caught.
8. [x] **Documentation and progress** — this plan, the requirements, the summary, `aidlc-state.md`, `audit.md`.
9. [ ] **Deploy and verify on the live stack** — rebuild worker and API, set the setting to `gemini` through the app's own settings function, restart the worker, confirm a real categorisation request goes to Gemini.

## Completion criteria
All steps `[x]`; suites pass; the live worker categorises through Gemini and the local option is unchanged.
