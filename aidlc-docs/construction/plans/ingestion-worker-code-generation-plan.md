# Code Generation Plan — Unit 3: Ingestion Worker Service

**Workspace root**: `/Volumes/1TB/projects/transactAgent`
**Code location**: `ingestion-worker/` directory at workspace root

## Unit Context

- **Stories implemented**: US-1.1, US-1.2 (execution half), US-1.3, US-1.4, US-2.1–2.3, US-3.4 (retro half), US-3.7 (conversion half), US-4.6 (conversion half)
- **Dependencies**: Unit 1 (`database` package)
- **External APIs**: Gemini (extraction), OpenRouter (categorization fallback), Google Drive (via `oauth_credentials` token written by Unit 2), exchangerate.host (FX fallback)
- **PBT-applicable pure functions** (Hypothesis, Partial PBT mode): similarity matcher, currency-conversion source-priority resolver, extraction-response schema validation round-trip

## Steps

- [x] Step 1: Project Structure Setup — created `pyproject.toml`, package skeleton, `config.py`, `db.py` (session-per-task), `heartbeat.py`
- [x] Step 2: External API Client Wrappers — created `clients/retry.py`, `clients/gemini_client.py`, `clients/openrouter_client.py`, `clients/drive_client.py`, `clients/fx_client.py`. **Gap caught while implementing `drive_client.py`**: refreshing a Drive access token needs `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` too, not just the stored refresh token — added to `config.py` and corrected `infrastructure-design.md` (had incorrectly said these weren't needed here).
- [ ] Step 3: Client Wrapper Unit Testing — `tests/test_retry.py` (retry/backoff behavior, mocked failures)
- [x] Step 4: Business Logic Generation — created `extraction/{schemas,prompts,service}.py`, `categorization/{similarity,llm_classifier,service,repository}.py`, `currency/{service,repository}.py`, `duplicate_detection/service.py`, `orchestrator/{pipeline,repository}.py`. Currency service split into a pure `resolve_conversion_source()` decision function (PBT target) + an I/O-performing `resolve_converted_amount()` wrapper.
- [x] Step 5: Business Logic Unit Testing (incl. PBT) — created `tests/{test_similarity, test_currency_service, test_extraction_schema}.py` (Hypothesis PBT for the 3 pure functions), `tests/{test_duplicate_detection, test_categorization_service, test_extraction_service, test_orchestrator_pipeline}.py`. **Actually executed** against real Postgres (testcontainers) with external LLM/Drive/FX clients mocked — found and fixed 3 real bugs (see audit.md): a pydantic-settings import-time env-var ordering bug, and two test-helper bugs (colliding hardcoded hash/username across multiple calls in one test) — plus confirmed a genuine, expected boundary case in the default similarity threshold (not a bug). Final: 45/45 passing.
- [x] Step 6: Business Logic Summary
- [x] Step 7: Repository Layer Generation — folded into Step 4 (`categorization/repository.py`, `currency/repository.py`, `orchestrator/repository.py` generated alongside their services, same pattern as Unit 2)
- [x] Step 8: Repository Layer Unit Testing — covered transitively by Step 5's tests
- [x] Step 9: Repository Layer Summary — folded into Step 6
- [x] Step 10: Frontend Components Generation — **N/A**, no UI in this unit
- [x] Step 11: API Layer Generation — **N/A**, this unit has no HTTP API (worker loop only); `main.py` (the loop entrypoint) is generated in Step 12 instead
- [x] Step 12: Worker Entrypoint Generation — created `main.py` (asyncio polling loop, one run/job per cycle per WR-8, session-boundary crossing via `db.merge()`, heartbeat touch, top-level exception guard so one bad poll cycle never kills the process)
- [x] Step 13: Worker Entrypoint Testing — created `tests/test_main_loop.py` (4 tests: run dispatched, job dispatched only when no run, no-op when nothing queued, heartbeat file creation)
- [x] Step 14: Database Migration Scripts — **N/A**, Unit 1 owns migrations; this unit only calls `run_migrations_with_lock()` at startup
- [x] Step 15: Documentation Generation — created `aidlc-docs/construction/ingestion-worker/code/{business-logic-summary,README}.md`
- [x] Step 16: Deployment Artifacts Generation — created `ingestion-worker/Dockerfile` (incl. `poppler-utils`), added `ingestion-worker` service to root `docker-compose.yml`, updated `.env.example`, updated shared `deployment-architecture.md`. Validated with `docker compose config` (parses cleanly).

## Story Traceability
US-1.1, 1.2(execution), 1.3, 1.4, 2.1-2.3, 3.4(retro), 3.7(conversion), 4.6(conversion) — all covered by Steps 2, 4, 12.

---

This plan is the single source of truth for Unit 3 Code Generation.
