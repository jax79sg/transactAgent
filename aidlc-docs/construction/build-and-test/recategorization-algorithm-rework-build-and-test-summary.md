# Build and Test Summary — Recategorization Algorithm Rework

Single unit affected: Ingestion Worker Service only. No API/Frontend SPA changes. One retroactively-added Database migration (`0016`).

## Environment note

This machine's `ingestion-worker/.venv` had a broken Python interpreter symlink (pointed at a `/usr/local/bin/python3` that no longer exists on this system, unrelated to this feature). Recreated it from `pyenv`'s `python3.12` and reinstalled dependencies (`pip install -e ../database -e ".[test]"`) before the suite could actually run.

## Unit tests

- **291/291 passing** (10 new tests: 5 in `TestReferenceCodeStripping` + 3 direction-related in `TestBuildEmbeddingText`/`test_embedding_text.py`, 2 new in `TestRecategorizeUnsureFromPrecedent` for WR-35's broadened-pool behavior; 1 test rewritten to mock the new `query_nearest_neighbors`-based approach; several other existing tests updated for the new `direction` parameter without behavior changes).
- `ruff check src/ tests/`: clean.
- `docker compose build ingestion-worker`: clean.

## Live verification (real running stack, real embedding infrastructure, zero data committed)

Redeployed the new image (`docker compose up -d ingestion-worker`), container healthy. Ran the actual deployed `recategorize_unsure_from_precedent` directly inside a temporary container (the new image, not yet the running one) against placeholder rows (marked `__wr35_live_verify__`), inside one DB transaction rolled back at the end — zero rows committed, real oMLX/Qdrant infrastructure exercised for real.

**Check A — the exact reported failure, reproduced then confirmed fixed**: a `MANUAL`-corrected "NOVALAND PTE. LT" transaction (Household) and an `UNSURE` "HITPAY PAYMENTS" transaction sharing PayNow boilerplate phrasing but a genuinely different real payee — the precise shape of the false positives found in the requirements evidence. **Result**: no match, no proposal at all (previously this pattern scored 75-83 and always produced a `PENDING` proposal).

**Check B — a genuine near-duplicate still matches (no overcorrection)**: same "NOVALAND" precedent, an `UNSURE` candidate differing by one trailing character in its reference code (rapidfuzz `token_sort_ratio` ≈ 98.77, real threshold cleared). **Result**: auto-applied correctly (`AUTO_APPLIED`, score 98.77, category updated to Household within the rolled-back session).

Both checks ran against the real `.env`-reconciled threshold (`0.82`) and real oMLX/Qdrant services. Transaction rolled back afterward — confirmed no placeholder rows persisted.

## WR-39 backfill (real, not rolled back — this is the actual deliverable)

`docker compose up -d ingestion-worker` triggered migration `0016` automatically at startup (this project's existing `run_migrations_with_lock` mechanism). Verified:
- `alembic_version` = `0016`.
- Immediately after: 6096 `Transaction` rows and all 14 `RecurringPayment` rows reset to `embedding_status = 'pending'` (only 50 `Transaction` rows were still `completed`, from very recent ingestion activity that started after the migration's `UPDATE ... WHERE embedding_status = 'completed'` ran).
- 15 seconds later: 250 rows already re-processed back to `completed` by the existing `processNextEmbeddingBatch` poll-cycle mechanism, zero errors in worker logs, container stayed healthy — the backfill is progressing in the background exactly as WR-26/WR-32's precedent mechanism already does, no new code path needed.
- **Categories confirmed untouched by construction**: the migration is a plain single-column `UPDATE ... SET embedding_status = 'pending'` (never touches `category_id`/`category_source`), and `processNextEmbeddingBatch` only calls `computeEmbedding`/`upsertEmbedding` and flips `embedding_status` — no categorization logic exists in that code path at all. The full backfill (~6000 rows) will continue completing in the background over the following minutes at the existing batch cadence.

## Final state

`transactagent-worker` healthy after redeploy and migration. `transactagent-api`, `transactagent-frontend`, `transactagent-db`, `transactagent-vector-db` all unaffected and healthy (this feature touched only the Ingestion Worker Service). Real user data untouched except for the intended, explicitly-approved `embedding_status` backfill — no category was changed, no real transaction's proposal history was altered. The independent LLM verification gate (originally-scoped FR-RAR-2) remains deferred, undocumented in code, exactly as decided during Requirements Analysis.
