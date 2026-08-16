# Build and Test Summary — Local Embedding-Based Semantic Similarity (Epic 9)

## Build Status: Success

`docker compose up -d --build` rebuilt all 3 changed images (`ingestion-worker`, `api-service`, `frontend`) and brought up the new `vector-db` service against the real, already-running project stack (6142 real transactions, 14 real recurring payments — this is the user's live personal data, not a fresh/empty DB). All 5 containers (`database`, `vector-db`, `api-service`, `ingestion-worker`, `frontend`) reached healthy status.

## Unit Test Summary

| Unit | Tests | Status |
|---|---|---|
| Database | 47/47 (up from 44) | Pass |
| Ingestion Worker Service | 233/233 (up from 179) | Pass |
| API Service | 175/175 (up from 171) | Pass |
| Frontend SPA | 83/83 (up from 81) | Pass |
| **Total** | **538/538** | **Pass** |

Zero regressions across all four units. `tsc -b` + `vite build` clean; `app.openapi()` schema generation clean (37 paths).

## Live Verification (against the real running stack)

- **Migration**: `alembic_version` reached `0010` via the app's own advisory-lock startup path (confirmed via `psql`, not assumed) — `0009` had already been applied by a prior feature, `0010` (`RecurringPayment.embedding_status`, `BR-25`) applied cleanly this time. All 6142 pre-existing `transactions` rows and all 14 pre-existing `recurring_payments` rows backfilled to `embedding_status = 'pending'` by the migration's `server_default` alone — confirmed via a live `GROUP BY` query, no separate UPDATE needed, same "single default unifies forward + backfill" pattern as migration `0009`.
- **`vector-db` (Qdrant)**: confirmed healthy; confirmed (via `qdrant-client` executed inside the live `ingestion-worker` container, not just the earlier temporary-container smoke test) that both collections (`transactions`, `recurring_payment_names`) exist with `size=768, distance=Cosine` exactly as configured — created automatically on worker startup via the real `ensure_collections()` call, visible in the worker's own logs (`Created vector store collection 'transactions'` / `'recurring_payment_names'`, both real `PUT .../collections/...` calls returning `200 OK` against the real Qdrant service, not mocked).
- **Graceful degradation confirmed live, not just in unit tests**: `EMBEDDING_BASE_URL` is genuinely unset in this deployment's `.env` (the user has not set up a local oMLX embedding server — a real, expected state per NFR-5, not a test artifact) — the worker started cleanly, ran multiple 5-second poll cycles with zero errors, and the new fifth `poll_once()` branch produced no error logs despite every `compute_embedding()` call returning `None` immediately. This is the single most important thing to prove live for a feature whose defining requirement (FR-10) is "never break anything when the optional dependency is absent," and it held.
- **API layer, real data**: `GET /transactions` against the live API (minted a real JWT via the app's own `issue_token`, per this project's established pattern) returned real transactions with `"embeddingStatus": "pending"` present and correctly valued (AR-21).
- **`AR-22`, live, both directions**: created a placeholder `RecurringPayment` (`__epic9_live_test__`, invented name/amount, never a real payee), manually set its `embedding_status` to `completed` via SQL to simulate a previously-embedded row, then called the real `PUT /recurring-payments/{id}` endpoint with a changed `name` — confirmed live that `embedding_status` reset to `pending`. Repeated with an update that changed only `expectedAmount`/`dueDay` (same `name`) — confirmed live that `embedding_status` stayed `completed`, untouched. Deleted the placeholder payment afterward and confirmed zero rows matching the test name pattern remain — no leftover test data, no real payee data touched or exposed.
- **Frontend**: confirmed the live `frontend` container serves the rebuilt bundle containing both the badge's tooltip text (`"Embedding: pending"`) and its `data-testid` (`embedding-status-badge`) — confirms the new code actually shipped in the deployed image, not just that it exists in source.

## What was NOT verified live

- **No real embedding computation end-to-end**: `EMBEDDING_BASE_URL` is unconfigured on this machine (oMLX for embeddings is a host-native, user-managed prerequisite per NFR-5, distinct from the already-running `omlx-server` instance behind `OPENROUTER_BASE_URL`, which serves a different model for categorization-LLM fallback text generation). The "happy path" — a transaction actually getting embedded, a real semantic match found via the vector store — was exercised only via the unit test suites (mocked `compute_embedding`/`query_nearest_neighbors`) and the earlier temporary-Qdrant-container API smoke test during Infrastructure Design, not against a real embedding model. Setting this up is the user's own follow-up step, not something this session can do on their behalf.
- **No browser-based visual verification**: confirmed the badge's markup/text ships in the live bundle (above), but did not open a real browser to visually confirm rendering/styling — no browser automation tool was available in this session (contrast this project's prior features, several of which did include a real-browser check).
- **No actual PDF ingestion run triggered**: would have exercised `categorize()`'s embedding-first path against real (already-`pending`, not-yet-embedded) historical transactions, but since embedding is unconfigured, this would only have proven the fallback path again (already proven live above) — not attempted, to avoid an unnecessary write against the user's real transaction history for no additional verification value.

## Overall Status

- **Build**: Success
- **All Tests**: Pass (538/538)
- **Live Verification**: Pass (migration, new infrastructure, graceful degradation, API contract, AR-22 both directions, frontend bundle) — real-embedding happy path and browser-visual checks explicitly deferred, per above
- **Ready for Operations**: Yes (Operations phase remains a placeholder per this project's established pattern — `docker compose up` already covers deployment)
