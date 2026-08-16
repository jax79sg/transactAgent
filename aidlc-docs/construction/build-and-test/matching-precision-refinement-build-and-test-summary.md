# Build and Test Summary — Matching Precision Refinement

Full stack rebuilt and redeployed against the real running project (`docker compose build` + `up -d --build`), all 4 units together, against the real live database (6142 real transactions, 14 real recurring payments, 122 real pre-existing pending recategorization proposals).

## Migrations

- `0011_categorization_disagreements.py` and `0012_reembed_after_price_bucket_text_change.py` both auto-applied live via the app's own advisory-lock startup path — confirmed via `alembic_version = 0012`.
- `0011`'s new column/table verified via `psql \d`: `transactions.llm_suggested_category_id` and `categorization_disagreements` (3 FKs to `categories`, correctly disambiguated) both match the designed shape exactly.
- `0012`'s data reset verified live: immediately after redeploy, `SELECT embedding_status, count(*) ...` showed 100 already re-completed within 15 seconds (worker draining the fresh `pending` backlog in real time), climbing to full 6142/6142 `completed` over the following minutes — watched end-to-end via `docker logs`, zero errors, zero restarts throughout.

## Mid-Build-and-Test design change (found live, not simulated)

Initial live testing of `classify_batch` against the user's real local model server (oMLX, serving `gemma-4-26b-a4b-it-4bit`) surfaced exactly the concern the original design (Question 4, "concurrent individual calls") was meant to manage, but via the wrong lever: a file with many transactions means many simultaneous HTTP requests to a single local server. The user asked to reconsider after seeing this live, requesting (1) a configurable concurrency cap — already built — and (2) true multi-transaction-per-prompt batching, which was not.

Resolved via 3 clarifying decisions (batch size default 10; malformed/partial batch entries fall back to individual calls only for those specific entries, not the whole batch; a Settings-page env-config UI was explicitly scoped OUT as a separate follow-up feature) and implemented as a genuine two-phase redesign of `classify_batch`:
1. **Batch phase**: descriptions chunked into groups of `llm_classification_batch_size` (10), each chunk classified via one prompt asking for a JSON array response, chunks run concurrently bounded by `llm_classification_concurrency` (5).
2. **Fallback phase**: any description the batch phase didn't return a validated answer for falls back to the original one-call-per-description path — only for those specific descriptions.

`matching-precision-refinement-requirements.md` (new "Post-Approval Change" section, FR-MPR-3 revised in place), Ingestion Worker `business-rules.md` (WR-27 revised in place with a dated revision note), and the Application Design plan doc (Key Design Resolution 2 revision) were all updated to document this rather than silently changing the code. New code: `openrouter_client.classify_descriptions_batch` (multi-description prompt + retry/exception mapping, mirroring `classify_description`), `llm_classifier.classify_batch_prompt` (JSON-array parsing, partial-validity handling, never raises), `categorization/service.py`'s `classify_batch` rewritten to the two-phase design, `config.py` +`llm_classification_batch_size`. 16 new/reworked tests (new `test_llm_classifier.py`, 11 tests covering valid/partial/malformed/exception JSON-parsing cases; `test_openrouter_client.py` +2; `TestClassifyBatch` in `test_categorization_service.py` reworked, +3 net) — 268/268 unit tests passing (up from 252).

**Live-verified against the real running oMLX server** (not mocked, not simulated) at each step before considering it done:
- A 6-description single-batch-prompt call: 1.04s, all 6 correctly parsed, including a correct `UNSURE` for a deliberately ambiguous description.
- A 12-description `classify_batch` call (chunked into 10+2, using the real live category whitelist from the database): 2.52s total, all 12 correctly classified into real user categories.
- Re-ran both checks again after rebuilding and redeploying the final image (not just the copied-in files used for the first live probe) to confirm the deployed container behaves identically: 3-description call, 1.21s, all correct.
- Docker itself and the local oMLX server both went down mid-session during this investigation (unrelated host resource contention, not a bug in this code) and were restarted by the user; the real Postgres/Qdrant data on bind-mounted volumes was confirmed intact throughout (`./data/postgres`, `./data/qdrant`), and the re-embed backlog resumed and completed cleanly after the restart with zero data loss.

## API Service live verification

- Minted a real JWT via the app's own `issue_token` against a real user row.
- `GET /recategorization/disagreements` and `GET /recategorization/proposals/pending-count` both confirmed live (empty list initially; pending count reflecting 122 real pre-existing proposals).
- Full resolve flow verified live end-to-end using an invented placeholder transaction + disagreement (`__mpr_live_test__`, never a real payee, inserted directly via SQL with a real bank_statement parent row to satisfy the FK): listed correctly (both candidate categories, transaction detail, score), pending count incremented, `POST .../resolve` with the LLM-sourced candidate correctly wrote `category_source = 'llm'` (not `manual`) to the transaction and returned the fully-updated DTO. All placeholder rows (`categorization_disagreements`, `transactions`, `bank_statements`) deleted afterward — confirmed zero leftover rows matching the test marker.

## Frontend

- `docker compose build frontend` (runs `tsc -b && vite build` internally) verified clean.
- Confirmed the live, deployed frontend container's served JS bundle contains the new `DisagreementTable` markup/testids (`disagreement-section`, `disagreement-row-`, `disagreement-use-similarity-`, `disagreement-use-llm-`, `disagreement-reject-`) via `grep` against the container's own `/usr/share/nginx/html` output.
- No live browser-based click-through this session (no browser automation tool available, consistent with this project's precedent on prior features under the same constraint) — covered instead by the 7 new Vitest component tests (empty-state, row rendering, both resolve paths, reject, no-bulk-controls, visual separation from `ProposalTable`) plus the API-level live verification above proving the exact same endpoints the UI calls work correctly end-to-end.

## Final state

All 5 containers (`transactagent-db`, `transactagent-vector-db`, `transactagent-worker`, `transactagent-api`, `transactagent-frontend`) healthy, zero restarts, zero errors in logs, real user data (6142 transactions, 14 recurring payments) untouched except for the intended, verified `embedding_status` re-embed sweep.

**Full unit test total across all 4 units for this feature**: 52 (Database) + 268 (Ingestion Worker) + 191 (API Service) + 90 (Frontend) = 601 tests passing, zero regressions.
