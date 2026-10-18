# Account Balance at a Point in Time — API Service Code Summary (Epic 13)

Design: `../functional-design/` (AR-51..AR-67; endpoint paths and shapes in `domain-entities.md`) and the amendments of 2026-10-18 to the requirements, stories and component methods. Plan: `aidlc-docs/construction/plans/api-service-account-balance-code-generation-plan.md`. Stories: US-13.2 to US-13.6 (the API side; the screens are the Frontend unit).

## What was built

| Area | Where | What |
|---|---|---|
| Pure arithmetic | `balances/calculation.py` | No database, no clock, exact `Decimal`. `balance_from_known`, `choose_reference` (nearest known balance, ties to the anchor then the earlier date), `deduplicate_by_date`, `balance_on_date`, `to_sgd` (half-up, the only rounding), `NetFlowIndex` (net flow over any interval from per-day totals, by prefix sums), month and date resolution, series dates and granularity, `statement_differences`, `period_gaps`. Its refusals carry the stable error code the service maps them to. |
| Account Management | `accounts/{router,service,repository,schemas}.py` | `GET /accounts`, `PATCH /accounts/{id}`, `PUT /accounts/{id}/anchor`, `POST /accounts/{id}/merge`. One request is one transaction (`get_db` commits on success and rolls back on any error), so a merge that fails halfway changes nothing; a merge locks both accounts in id order and re-checks its preconditions inside the transaction. |
| Balances | `balances/{router,service,repository,schemas}.py` | `GET /balances?date=` or `?month=`, `GET /balances/series?from=&to=&granularity=`, `GET /balances/discrepancies`. Read-only; the database sums net flows and the series reads one daily-totals set per account, so transactions are never loaded into memory. |
| Errors | `errors.py` | 17 new typed errors (the 18th code, `invalid_date_range`, reuses the existing class) in the existing `ErrorResponse` shape. |
| Settings | `config.py`, `app_settings/{catalog,validation}.py` | `reporting_time_zone` (default `Asia/Singapore`) and `balance_mismatch_tolerance` (default 0.00), category "Balances", owned by the API Service; a new `time_zone` value format in the validation. The catalog is 55 entries. A change takes effect when the API restarts, like the other API-owned settings. |
| Wiring | `main.py` | Both routers registered; **`PATCH` added to the CORS allowed methods** (the browser would otherwise refuse the rename call). |
| Shared | `schemas.py` | A `Money` type: an exact amount that is always written to JSON as a two-place string. |

## Differences from the plan, found while generating

- The `Money` type went into the existing shared `schemas.py` (one small addition not listed in the plan), not into a feature folder, because both features use it.
- The settings catalog module also asserts its own size at import, and that assertion (53 to 55) was updated along with the two tests the plan named.
- The existing `InvalidDateRangeError` is reused for the date-range codes; a lookup date before 2000-01-01 is reported as `invalid_date_range`.
- A lookup reads each net flow with a database sum, and the series and discrepancies use the per-day totals index. They are different code paths to the same figure, so a test asserts they agree at every plotted date, for every account (and so does the real-data check below).

## How it was tested

**713 API Service tests pass** (467 existing + 246 new), `ruff check src tests` is clean, the whole suite was run with both Hypothesis profiles (`dev`, and `ci` which is derandomized). The 467 existing tests pass unchanged except the two catalog-count assertions (53 to 55).

New tests: `test_balances_calculation.py` (59: properties and examples), `test_balances_repository.py` and `test_accounts_repository.py` (27, against real PostgreSQL), `test_accounts_service.py` (44, including a **real two-connection race** where the second merge is blocked and then refused) and `test_balances_service.py` (42), `test_api_accounts.py` (26, including the CORS preflight for `PATCH`) and `test_api_balances.py` (27), plus the new-settings tests in `test_settings_validation.py`.

**Properties checked** (PBT-02, PBT-03, PBT-07, PBT-08, PBT-09; generators are shared in `tests/balance_strategies.py`): the balance on a known date is that known balance; working forward and then back returns the start; balances on one side of the known date differ by exactly the net flow between them; every balance is an exact two-place decimal; the index agrees with adding up the days; net flow adds up across a split date; the chosen reference is never farther than another known balance, does not depend on input order, and an anchor wins a tie; at most one known balance per date and an anchor is never lost; series dates lie in range, in order, without repeats, month points are month ends plus the range end; closing balances that follow the anchor's own arithmetic show no difference and no gap; period gaps add up to the whole interval's gap (telescoping); a larger tolerance never reports more; SGD conversion is within half a cent.

**Mutation check** (a scratch copy, one deliberate defect at a time; every defect must make a test fail): **45 of 45 caught.** 20 on the pure module (the balance sign, the farthest reference, each tie rule, the dedupe preference, the index boundary, half-even and truncating rounding, the monthly range end, the 92-day threshold, month clamping, the current month, a future date, both discrepancy signs, the inclusive tolerance, a missing day, the 1,500 limit) and 25 on the services, repositories, routers and CORS (the closing balances left out of the lookup, a total of 0.00 for nothing included, never-approximate conversion, an 11-month default range, the tolerance setting ignored, the unlinked notice dropped, the time zone ignored, missing accounts not listed, each merge precondition removed, keys left behind, the type rule reversed, a future anchor date and a three-place balance allowed, retyping not marking the user's choice, an anchor on any account type, both net-flow boundaries, the oldest FX rate chosen, credit cards listed as deposit, the login removed from each router, `PATCH` removed from CORS, and the tolerance range changed).

## Verified against the real data (on a scratch copy; the live database was never written)

A read-only dump of the live database was restored into a throw-away PostgreSQL and the API's real code run on it, with an anchor set for each of the 12 deposit accounts that has a printed closing balance. The scratch copy and the dump were deleted afterwards.

| Check | Result |
|---|---|
| Period gaps against the independent analysis made before the design | **28 of 113 intervals** do not reconcile, exactly as found separately; the two small ones are SGD 0.15 and 0.16; 16 are over SGD 100 |
| On every printed closing date the balance equals the statement | **125 of 125** |
| Independent recomputation (raw SQL and plain Python written from the requirement, sharing no code) on 40 random dates, every anchored account | **480 of 480** balances identical |
| Series equals lookup at 25 sampled dates | 25 of 25 |
| Speed (NFR-AB-5, under one second) | lookup 16 ms; default 12-month series 11 ms; 12-month **daily** series 32 ms; discrepancies 11 ms |
| Transactions linked to no account | exactly the 99 July 2026 GXS Bank transactions, net SGD 18.65, ingested through 2026-09-30 |
| Merge of "DBS 6220" into "DBS / POSB 6220" | works: the survivor then has 5 statements and 15 transactions |
| Merge of the two "GXS Bank cket" accounts | **correctly refused** (`merge_appear_together`): one statement lists both, so they are different accounts (probably two sections of one GXS statement whose account identifier was read as "cket"); the way to tell them apart is to rename them |

## Contract for the Frontend unit

Endpoint paths, request and response shapes and error codes are exactly those in `functional-design/domain-entities.md` and `business-rules.md` (AR-64). Points the Frontend must handle: an account's `basis` says what its figure was worked from; a null per-account value in the series is a gap, never zero; `combinedTotalSgd` is null when no account is included; the lookup's `unlinkedTransactions` notice and `excluded` list; `typeSetByUser`; money is always a string such as `"1030.00"`; a malformed date is a framework 422, every business-rule refusal is the usual `{error, message, details}`.

## Not done here

The screens (Frontend unit), the API image rebuild and restart (done at deployment, after the Frontend unit, like every earlier release), and anything in the user guide.
