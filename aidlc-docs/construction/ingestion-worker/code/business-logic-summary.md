# Business Logic + Repository Layer Summary — Unit 3: Ingestion Worker Service

| Domain area | Client wrapper | Service (business rules) | Repository | Tests |
|---|---|---|---|---|
| Drive access | `clients/drive_client.py` (reads `oauth_credentials`, refreshes token) | — | — | Covered via `test_orchestrator_pipeline.py` (mocked at client boundary) |
| Extraction | `clients/gemini_client.py` | `extraction/service.py` (WR-1, WR-2) | — | `test_extraction_service.py` (7 tests), `test_extraction_schema.py` (Hypothesis round-trip) |
| Categorization | `clients/openrouter_client.py` | `categorization/{similarity, llm_classifier, service}.py` (WR-3, WR-4, WR-5, WR-9, WR-10) | `categorization/repository.py` | `test_similarity.py` (Hypothesis), `test_categorization_service.py` |
| Currency conversion | `clients/fx_client.py` | `currency/service.py` (WR-6, split into pure `resolve_conversion_source()` + I/O `resolve_converted_amount()`) | `currency/repository.py` | `test_currency_service.py` (Hypothesis) |
| Duplicate detection | — | `duplicate_detection/service.py` | — (queries `BankStatement` directly) | `test_duplicate_detection.py` |
| Orchestration | — | `orchestrator/pipeline.py` (WR-7, WR-8, NFR-2.2) | `orchestrator/repository.py` | `test_orchestrator_pipeline.py` (3 integration-style tests, real Postgres + mocked external clients) |
| Worker loop | — | `main.py` | — | `test_main_loop.py` (dispatch logic) |

**PBT coverage** (Partial mode, Hypothesis): `test_similarity.py`, `test_currency_service.py`, `test_extraction_schema.py` — all 3 targeting genuinely pure functions with no I/O.

**Bugs found via actual execution** (not just `py_compile`) — see `audit.md` for full detail:
1. `pydantic-settings` validates at construction time (module import), not lazily — env-var defaults set inside a pytest fixture were too late for modules importing `config` at collection time; fixed by moving them to `conftest.py` module level.
2. Two test-helper bugs (hardcoded hash/username colliding across multiple calls within one test) — application code was correct, tests needed fixing.
3. Confirmed (not a bug) a real boundary case in the default 85-point similarity threshold: "NTUC FAIRPRICE #123" vs "#456" scores ~84 (just under), while a single-digit change scores ~95 — informs future threshold tuning.

**Epic 6 (Recategorization Review Panel, added 2026-08-02)**: `recategorize_unsure_from_precedent` (WR-9/WR-10) broadened to search two buckets and record every outcome as a `RecategorizationProposal` row (`categorization/repository.py`'s new `find_categorized_transactions_excluding()` and `record_proposal()`), split by a new `recategorization_auto_apply_threshold` config value (default 97.0, above the existing 85.0 `similarity_threshold`). Real rapidfuzz scores computed (not assumed) to build correct test fixtures for both sides of the new threshold: an exact-string-match pair scores 100 (auto-applies), the original "#2"-suffix pair from the pre-existing test scores ~93 (now falls into the new pending band, since it clears the old 85-point bar but not the new 97-point one) — required updating that existing test's expected outcome, not just adding new tests. 4 new tests added (`test_categorization_service.py`, `TestRecategorizeUnsureFromPrecedent`), full suite verified at 72/72 passing (up from 68).
