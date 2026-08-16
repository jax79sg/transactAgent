# Embedding Status Exposure & Write-Path — Code Summary (Epic 9)

Small, surgical change — no new component, no new files. Implements AR-21 and AR-22.

| File | Change |
|---|---|
| `transactions/schemas.py` | `TransactionDTO` +`embedding_status: str` (required — every `Transaction` row has a value, Database `BR-24`) |
| `transactions/router.py` | `_to_dto()` +`embedding_status=txn.embedding_status.value` |
| `recategorization/router.py` | `_to_transaction_dto()` +`embedding_status=txn.embedding_status.value` (reuses `TransactionDTO` for `ProposalDTO.candidate_transaction`) |
| `recurring_payments/service.py` | `_to_match_dto()` +`embedding_status=txn.embedding_status.value` (reuses `TransactionDTO` for `RecurringPaymentMatchDTO.transaction`); `update_recurring_payment()` resets `embedding_status` to `pending` when (and only when) the update changes `name` (AR-22) |

## Real thing caught making `embedding_status` required

`TransactionDTO` is constructed in **three** places (`transactions/router.py`, `recategorization/router.py`, `recurring_payments/service.py`'s `_to_match_dto`), not one — making the new field required (rather than defaulted) meant all three had to be updated together, or the two not-yet-updated ones would raise a Pydantic validation error the moment their endpoint was hit. Caught by grepping for every `TransactionDTO(` call site before running the suite, not discovered as a test failure — the full 175-test suite passed clean on the first run after all three were updated together.

## `RecurringPaymentDTO` deliberately does NOT expose `embedding_status`

Unlike `Transaction`, a `RecurringPayment`'s embedding status has no UI purpose (FR-7's badge is Transaction-only, US-9.1) — it exists solely to drive the Ingestion Worker's `recurring_payment_names` vector-store population (Database `BR-25`). Adding it to the DTO would be exposing an internal implementation detail with no consumer, so it isn't — `create_recurring_payment`'s reliance on the column's own default, and `update_recurring_payment`'s reset-on-rename, are both invisible to any API response, verified directly against the ORM row in tests instead.

## Tests

- `tests/test_recurring_payments_service.py`: +3 tests — create defaults to `pending`, name-changing update resets to `pending`, non-name update leaves it untouched
- `tests/test_api_transactions.py`: +1 test — `embeddingStatus` present and `"pending"` in a fresh transaction's API response

Full suite: **175/175 passing** (up from 171). OpenAPI schema smoke-tested (`app.openapi()`), 37 paths, no errors.
