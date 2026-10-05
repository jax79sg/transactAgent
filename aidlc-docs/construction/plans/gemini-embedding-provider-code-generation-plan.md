# Code Generation Plan — Gemini Embedding Provider (2026-10-05)

**Requirements**: `inception/requirements/gemini-embedding-provider-requirements.md`. **Units**: Ingestion Worker, API Service (catalog + mirror), deployment files, the tooling folder. Frontend unchanged. **Branch**: `feature/account-balance` (PR #25). **Approval**: the user's request of 2026-10-05, under the standing instruction.

## Steps
1. [x] **Research and probe** — Gemini Embedding 2 is current (GA 2026-05-20); through Google's OpenAI-compatible endpoint `gemini-embedding-2` works, honours `dimensions`, returns normalised vectors and batches.
2. [x] **Calibrate** on the user's 6,645 labelled transactions: raw versus the classification prefix, thresholds, fuzzy-text context (see the requirements).
3. [x] **Worker config** — `embedding_provider`, `gemini_embedding_model`.
4. [x] **Worker client** — `embedding/client.py`: `_provider()`; gemini asks for `embedding_dimensions`, prefixes the task, 15 s bounded timeout, no retry, wrong-size vector = unavailable; local unchanged.
5. [x] **API** — two catalog entries (50 settings), the `embedding_*` descriptions marked local-only, the display mirror.
6. [x] **Deployment files** — `EMBEDDING_PROVIDER` and `GEMINI_EMBEDDING_MODEL` in `docker-compose.yml` (both backends) and `.env.example`.
7. [x] **Tests** — worker 20 new (`test_embedding_client.py`, `test_config.py`); API 10 new and the count assertions (`test_settings_validation.py`, `test_api_settings.py`).
8. [x] **Verification** — worker 711 pass, API 373 pass, `ruff` clean in both; 13 mutations each caught (provider ignored; another key, model name, dimension or prefix; prefix not applied; wrong-size vector accepted; Gemini switched off by the empty local endpoint; timeout not applied; value not validated; either default flipped).
9. [x] **Tool** — the calibration script kept as `integration-tests/embedding_calibration.py` with instructions.
10. [x] **Documentation and progress** — this plan, the requirements, the summary, `aidlc-state.md`, `audit.md`.
11. [ ] **Deploy** (after the backfill finishes, because a worker restart would fail its in-progress run): rebuild, recreate, set `embedding_provider` = gemini and both thresholds through the app's own settings function, restore `embedding_base_url`, restart the worker, confirm that a real embedding reaches Gemini and the pending transactions are embedded.

## Completion criteria
All steps `[x]`; suites pass; every transaction embedded through Gemini; the local option unchanged.
