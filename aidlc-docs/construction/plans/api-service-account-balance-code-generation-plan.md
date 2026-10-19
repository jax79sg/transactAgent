# Code Generation Plan — API Service Unit — Account Balance at a Point in Time (Epic 13)

**This plan is the single source of truth for API Service Code Generation of this feature.** Part 1 (this document) is for approval; no code is written until it is approved.

**Unit**: API Service (Unit 2). **Stories**: US-13.2, US-13.3, US-13.4, US-13.5, US-13.6 (the API side; the screens are the Frontend unit). US-13.1 and US-13.7 were delivered by the Database and Ingestion Worker units.
**Design source (approved 2026-10-18)**: `aidlc-docs/construction/api-service/functional-design/` (rules AR-51 to AR-67, `business-logic-model.md`, `domain-entities.md`) and the amendments of 2026-10-18 to `account-balance-requirements.md`, `account-balance-stories.md` and `component-methods.md`.
**Dependencies**: Database unit (tables `accounts`, `account_keys`, `balance_anchors`, `statement_accounts`, `transactions.statement_account_id`, `fx_rate_cache`: all exist and are deployed; **no migration is needed**). Ingestion Worker (supplies the data; no code dependency). The Frontend unit depends on this one and is not started until it is approved.
**Entities owned by this unit**: none. It reads and writes the Database unit's tables (writes only to `accounts`, `balance_anchors`, `account_keys`, `statement_accounts`, AR-67).
**Code location**: workspace root, `api-service/` (brownfield: existing files are modified in place, new feature folders follow the existing one-folder-per-feature pattern). Documentation: `aidlc-docs/construction/api-service/code/` (markdown only). Nothing is written under `aidlc-docs/` except documentation.

## Approach

Two new feature folders in the existing layout (`router.py`, `service.py`, `repository.py`, `schemas.py`), plus one **pure** module so the arithmetic is isolated and property-testable:

- `api_service/accounts/` — Account Management (AR-51..AR-54, AR-64, AR-65): list, rename and retype, set or replace the anchor, merge.
- `api_service/balances/` — Balance (AR-55..AR-62, AR-66): `calculation.py` (pure: no database, no clock), then `repository.py`, `service.py`, `schemas.py`, `router.py`.
- Shared: typed errors (AR-64), two settings (AR-63), router registration.

Order of work: the pure module first and tested hard, then the data layer, then services, then the HTTP layer, then verification against a copy of the real data.

## Decisions found while planning (for review at approval)

1. **`PATCH` is blocked by the API's CORS configuration.** The approved design uses `PATCH /accounts/{id}`, but `main.py` allows only `GET, POST, PUT, DELETE`, and the Frontend (served from another origin) would be refused by the browser. This plan **adds `PATCH` to the allowed methods** (one word, with a test of the preflight response). The alternative is to change the design to `PUT /accounts/{id}`, which is what every other update in this API uses; say so at approval if you prefer it.
2. **Property-based testing needs a dependency.** `hypothesis` is already used by the Ingestion Worker but is not an API Service dependency. The plan adds `hypothesis>=6.100,<7.0` to the API Service's **test** extra only (nothing is added to the runtime image) and updates `uv.lock` minimally.
3. **Two tests pin the settings catalog size** (`test_settings_validation.py` and `test_api_settings.py`, currently 53). Adding two settings makes it 55; both assertions are updated deliberately, not loosened.
4. **A new setting value format, `time_zone`,** is added to the catalog validation (`app_settings/validation.py`), alongside `currency_code` and the others, so `reporting_time_zone` is checked against the platform's time-zone database. The running API image resolves it already (checked: `Asia/Singapore`, 486 zones known).
5. **The live database is never written during verification.** Verification against real data (Step 17) runs on a scratch copy restored from a read-only dump.

## Steps

1. [x] **Branch**: work continues on `feature/account-balance-completion` (draft PR #50), the repository's established feature-branch workflow. Nothing goes to `main` directly.

2. [x] **Test infrastructure for property-based testing (PBT-08, PBT-09)** — modify `api-service/pyproject.toml` (add `hypothesis>=6.100,<7.0` to the `test` extra) and `api-service/uv.lock` (`uv lock`, minimal diff); modify `api-service/tests/conftest.py` to register two Hypothesis profiles: `dev` (random, prints the reproduction blob on failure) and `ci` (derandomized, so every CI run is identical and a failure replays locally), chosen by the `CI` environment variable that GitHub Actions sets. Shrinking is left enabled (never overridden).

3. [x] **Shared generators (PBT-07)** — create `api-service/tests/balance_strategies.py`: reusable, domain-shaped Hypothesis strategies, not raw primitives: `money()` (exact two-place decimals, negative and zero included, bounded to the column range), `calendar_dates()` (a realistic window incl. month ends and leap days), `known_balances()` (a known balance with source, date and record order), `dated_flows()` (a list of dated signed flows for one account). Used by every property test below.

4. [x] **Typed errors (AR-64)** — modify `api-service/src/api_service/errors.py`: the 18 new codes with their statuses (404, 400, 409), same `ApiError` shape and handler, so the Frontend keeps one error path.

5. [x] **Settings (AR-63)** — modify `api_service/config.py` (fields `reporting_time_zone: str = "Asia/Singapore"`, `balance_mismatch_tolerance: Decimal = Decimal("0.00")`); modify `api_service/app_settings/catalog.py` (new category "Balances"; two `SettingSpec` entries, owned by the API Service, class standard; tolerance as a float 0.0 to 1000.0, time zone with the new `time_zone` format; explanatory descriptions that state "takes effect when the API restarts"); modify `api_service/app_settings/validation.py` (the `time_zone` format check, reusing the platform's time-zone database). Update the two pinned catalog counts, 53 to 55.

6. [x] **Business logic — the pure calculation module (AR-55, AR-56, AR-57, AR-59, AR-61)** — create `api_service/balances/calculation.py`, no I/O and no clock, exact `Decimal` only:
   - `KnownBalance` (frozen: balance, date, source `anchor` or `statement_closing`, statement id, record order);
   - `balance_from_known(known, target, net_flow)` (forward adds, backward subtracts, FR-AB-7);
   - `choose_reference(known_balances, target)` (nearest by calendar days; ties to the anchor, then the earlier date; same-date duplicates to the anchor, then the last recorded);
   - `deduplicate_by_date(known_balances)` (AR-55, also used by the period gaps);
   - `to_sgd(amount, rate)` (half-up to two places, the only rounding anywhere);
   - `resolve_month(month, today)` and `validate_lookup_date(date, today)` (A-5, AR-57);
   - `series_dates(start, end, granularity)` and `resolve_granularity(start, end, requested)` (AR-61);
   - `statement_differences(...)` and `period_gaps(...)` (AR-62, given the anchor, the closings and a net-flow function, so they stay pure and testable).

7. [x] **Business logic unit testing, example-based and property-based** — create `api-service/tests/test_balances_calculation.py`:
   - *Properties (PBT-02, PBT-03)*, using the shared generators: (a) **identity**: the balance at a known date equals that known balance; (b) **round trip**: working forward from a known balance to D and then backward from D to the original date returns the original balance; (c) **additivity**: for dates a ≤ b ≤ c on one side of the known date, balance(c) − balance(b) equals the net flow in (b, c]; (d) **nearest**: the chosen reference is never farther from D than any other known balance, and is deterministic whatever the input order; (e) **the anchor wins ties**; (f) **dedupe**: at most one known balance per date, the anchor kept; (g) **series consistency**: for any range, every plotted date is inside the range and, in month mode, is a month end or the range end, in day mode every day appears once; (h) **discrepancy invariant**: a statement difference is zero for every closing balance generated to agree with the anchor's own arithmetic, and a period gap is zero when the printed change equals the transaction net; (i) **exactness**: no float ever appears and results have at most two decimal places.
   - *Examples*: the month-shortcut cases (past month, current month, February in a leap year, a future month refused), future and ancient dates refused, rounding half-up at the boundary, granularity `auto` at 92 and 93 days, month mode when the range ends mid-month and when it contains no month end, each tie rule.

8. [x] **Business logic summary** — fold into Step 18's code summary (the repository's earlier plans do the same): for this unit the business logic is `calculation.py`; its rules are traced to AR numbers in module docstrings.

9. [x] **Repository layer — Account Management** — create `api_service/accounts/__init__.py` and `repository.py`: list accounts with their keys, anchor and the per-account counts and latest transaction date in few queries (not one per account); get accounts for update with row locks; statements that list both of two accounts; re-point statement sections and keys; upsert the anchor as one conditional write; delete an account; read the previous anchor.

10. [x] **Repository layer — Balances** — create `api_service/balances/__init__.py` and `repository.py`: deposit accounts with their anchor and printed closing balances (one read); the net of an account's transactions after one date up to and including another, summed by the database; per-account daily totals over a range (for the series, so transactions are never loaded into memory, AR-66); the latest transaction date overall and per account; the unlinked-transactions notice inputs (count, banks, dates, net per currency); the nearest earlier cached FX rate on or before a date (AR-59).

11. [x] **Repository layer unit testing** — create `api-service/tests/test_accounts_repository.py` and `test_balances_repository.py` against a real PostgreSQL (testcontainers, the suite's existing fixture): net flow boundaries (the day after the earlier date is in, the earlier date is out, the later date is in); transactions with no account link are excluded and counted by the notice query; credit-card accounts never returned as deposit; the FX query picks the nearest earlier date and returns nothing when none is on or before; the list query counts match; the anchor upsert replaces and returns the previous value.

12. [x] **Service layer — Account Management (AR-51..AR-54, AR-64, AR-65)** — create `api_service/accounts/service.py`: list (ordering, `canHaveAnchor`), rename and retype (validation, the user-set flag, the anchor row kept), set anchor (validation order and codes, "today" from the reporting time zone), merge (lock both, preconditions in the designed order, anchor choice, type reconciliation, re-point, delete, all in one transaction).

13. [x] **Service layer — Balances (AR-55..AR-62, AR-66)** — create `api_service/balances/service.py`: "today" from the setting; lookup (date or month, per-account status and basis, SGD conversion, combined total from the displayed per-account figures, exclusions, ingested-through dates, the unlinked notice); series (defaults of the last 12 months, granularity, the 1,500-point limit, the same per-date function as the lookup, gaps, missing accounts); discrepancies (anchor-only statement differences, period gaps, tolerance from the setting).

14. [x] **Service layer unit testing** — create `api-service/tests/test_accounts_service.py` and `test_balances_service.py` against real PostgreSQL: every refusal code of AR-54 and AR-53 in the designed order; a merge that moves everything and one that fails halfway leaves nothing changed; two merge attempts racing; the type reconciliation cases; **lookup equals series at every plotted date, for every account** (US-13.5 consistency); nearest-known-balance on a statement date equals the statement; the anchor-only difference vanishes once the anchor is corrected (US-13.6 resolution); no anchor means no balance, no check and no warning; foreign-currency balance with an exact, an earlier and no FX rate; unlinked notice present and absent; tolerance 0.00 versus raised; credit-card and unknown accounts never appear; the default series range and the month and day limits; a stale account shows its own latest date.

15. [x] **API layer** — create `api_service/accounts/schemas.py`, `router.py` and `api_service/balances/schemas.py`, `router.py` (camelCase DTOs as designed, `/accounts` and `/balances` routers behind `get_current_user_id`, the static `/balances/series` and `/balances/discrepancies` paths declared before any parameterised route); modify `api_service/main.py` (register both routers; add `PATCH` to the CORS allowed methods, Decision 1).

16. [x] **API layer unit testing** — create `api-service/tests/test_api_accounts.py` and `test_api_balances.py` with the FastAPI test client: every endpoint returns 401 without a login (NFR-AB-6); each endpoint's success shape matches `domain-entities.md` field for field; each error code and status of AR-64; a CORS preflight for `PATCH /accounts/{id}` is allowed and an unknown method still is not; `GET /balances` with neither or both of `date` and `month` is refused; the route order cannot shadow `/balances/series`; an existing endpoint (categories, transactions) still behaves as before (NFR-AB-8).

17. [x] **Live-data verification on a scratch copy (the live database is never written)** — dump the live database read-only, restore it into a throw-away PostgreSQL, run the API's real code against it, and check: (a) the 14 deposit accounts list, with the known duplicates visible; (b) **independent cross-check**: the service's period gaps equal the 28 mismatching intervals of 113 found separately in this stage's analysis (85 reconcile), and the same 2 small ones (0.15 and 0.16) are the only ones under SGD 1; (c) setting an anchor for each account in the scratch copy, a lookup and the default 12-month series each complete in **under one second** (NFR-AB-5), and the series equals the lookup at sampled dates; (d) on every statement date the nearest-known-balance figure equals the printed closing balance; (e) a merge of the two "GXS Bank cket" accounts and of "DBS 6220" into "DBS / POSB 6220" works and is refused where it must be; (f) the unlinked notice reports exactly the 99 July 2026 GXS transactions.

18. [x] **Static checks and the full suite** — `ruff check src tests` clean with the unit's configuration; the **entire** API Service suite (existing 467 plus the new ones) passing against real PostgreSQL; PBT run once with the dev profile and once with the CI profile, the seed or blob logged.

19. [x] **Documentation Generation** — create `aidlc-docs/construction/api-service/code/account-balance-summary.md` (files created and modified, endpoints, settings, how each AR rule is implemented and tested, the verification results of Step 17, how to reproduce a failing property test); check `aidlc-docs/construction/api-service/code/README.md` and `api-service/README.md` (if present) for endpoint or settings lists needing the same update.

20. [x] **Deployment Artifacts** — N/A for this unit: no new container, port, environment variable or compose change; no migration; the new settings need no `.env.example` entry (they have defaults and live in the override file). The API image is rebuilt and the API restarted at deployment, after the Frontend unit, as in every earlier release.

21. [x] **Progress** — mark each step `[x]` as it completes; mark US-13.2 to US-13.6 `[x]` for their API layer in the "Story coverage" table; update `aidlc-state.md`; confirm no duplicate files were created and that nothing changed outside `api-service/`, `aidlc-docs/` and (only if needed) the CI-neutral test configuration.

## Story coverage (API layer)

| Story | What this unit provides | Steps |
|---|---|---|
| [x] US-13.2 tidy accounts | list, rename, retype, merge with its refusals | 9, 11, 12, 14, 15, 16 |
| [x] US-13.3 anchor | set or replace the end-of-day anchor, validation, previous value | 9, 12, 14, 15, 16 |
| [x] US-13.4 lookup | date or month lookup, nearest known balance, SGD, exclusions, ingested-through, unlinked notice | 6, 7, 10, 13, 14, 15, 16 |
| [x] US-13.5 chart | series with automatic and forced granularity, 12-month default, gaps, lookup consistency | 6, 7, 10, 13, 14, 15, 16 |
| [x] US-13.6 discrepancy | statement differences, period gaps, tolerance setting | 5, 6, 7, 13, 14 |

## Completion criteria for this unit
- All steps above marked `[x]`.
- The entire API Service suite passing against a real PostgreSQL, including every new test and the property-based tests under both profiles.
- Step 17's real-data checks pass, including the independent period-gap cross-check and the under-one-second timing.
- No existing file duplicated; no change outside `api-service/` and `aidlc-docs/`; the live database untouched.

## Scope estimate

21 steps. 11 new source files (two feature folders, one of them holding the pure module), 6 modified source files (`errors.py`, `config.py`, `main.py`, the catalog, its validation, `pyproject.toml`, plus the regenerated `uv.lock`), 8 new test files and 3 modified (`conftest.py` and the two tests that pin the catalog size), plus the summary document. Expected size: roughly 150 to 200 new tests.


## Generation record (2026-10-18)

All 21 steps complete. Deviations from the plan, each small and listed in `construction/api-service/code/account-balance-summary.md`: the `Money` type was added to the shared `schemas.py` (7 modified source files, not 6); the settings catalog's own import-time size assertion was updated along with the two tests the plan named; the existing `InvalidDateRangeError` is reused for the range codes. Results: 713 tests pass (467 existing + 246 new) under both Hypothesis profiles; `ruff` clean; 45 of 45 deliberate breakages caught; the real-data checks of Step 17 all agree with the independent analysis. The live database was not written and the scratch copy and its dump were deleted.
