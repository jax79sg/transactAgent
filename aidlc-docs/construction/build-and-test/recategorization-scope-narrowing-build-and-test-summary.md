# Build and Test Summary — Recategorization Scope Narrowing

Single unit affected: Ingestion Worker Service only. No schema change, no API change, no UI change.

## Unit tests

- 274/274 passing (down from 276 — net of 3 tests removed for now-unreachable Bucket B scenarios, 1 added confirming the new no-proposal-at-all behavior).
- `ruff check` clean.
- `docker compose build ingestion-worker` verified clean.

## Live verification (real running stack, real code, zero data committed)

Redeployed the new image (`docker compose up -d ingestion-worker`), container healthy. Rather than triggering a real correction against real user data, ran the actual deployed `recategorize_unsure_from_precedent` function directly inside the live container against 3 placeholder rows (clearly marked `__rsn_live_verify__`, inside one DB transaction, rolled back at the end — zero rows committed, zero leftovers):

- **Source**: a `MANUAL`-corrected placeholder transaction, "IKEA FURNITURE STORE" → a placeholder "household"-style category.
- **Already-categorized candidate**: identical description, currently `SIMILARITY`-sourced in a placeholder "groceries"-style category — an exact-match (score 100) that, under the old Bucket B, would have produced a `PENDING` proposal even at this score (per the now-removed WR-10).
- **UNSURE candidate**: identical description, `UNSURE`-sourced — to confirm the surviving bucket's behavior is genuinely unchanged.

**Result**: the already-categorized candidate received **zero** proposal (`None`, correctly absent — previously would have been `PENDING`/`CATEGORIZED`). The `UNSURE` candidate auto-applied exactly as before (`AUTO_APPLIED`/`UNSURE`, category correctly updated to the source's corrected category). Transaction rolled back afterward — confirmed no placeholder rows persisted.

## Final state

`transactagent-worker` healthy after redeploy, zero errors in logs, real user data untouched (no real correction was triggered — verification used only placeholder rows in a rolled-back transaction). Existing pending proposals from the old, broader scope (real historical `CATEGORIZED`-bucket rows) are untouched per FR-RSN-3 — left for the user to review individually on the Review page as before.
