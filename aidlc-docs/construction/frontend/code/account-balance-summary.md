# Account Balance at a Point in Time — Frontend SPA Code Summary (Epic 13)

Design: `../functional-design/` (the Epic 13 sections of `frontend-components.md` and `business-logic-model.md`) and the API contract in `construction/api-service/functional-design/domain-entities.md` **as corrected 2026-10-18** (three corrections found while building this unit: the series range is `start`/`end` not `from`/`to`; the discrepancy DTOs' statement ids may be null; an `fx_unavailable` account still reports its own-currency balance). Plan: `aidlc-docs/construction/plans/frontend-account-balance-code-generation-plan.md` (20 steps). Stories: US-13.2 to US-13.6 (the screens; the API side was built in the API Service unit, and US-13.1/US-13.7 in the Database and Ingestion Worker units).

## What was built

| Area | Where | What |
|---|---|---|
| Types and API modules | `src/api/types.ts` (+Epic 13 DTOs), `src/api/client.ts` (+`PATCH`), `src/api/accounts.ts`, `src/api/balances.ts` | Mirrors the API's DTOs field for field; money and dates stay strings end to end. |
| Exact money | `src/lib/money.ts` | `toCents`/`fromCents` (BigInt cents, never floating point), `formatAmount`/`formatMoney` (thousands-grouped, no negative zero), `parseAmountInput` (refuses more than two decimals rather than rounding). |
| Balance wording and rules | `src/lib/balances.ts` | `localToday`/`addDays`/`dayBefore`, `describeBasis`/`describeLookup`, `mergeTypeOutcome` (mirrors the API's AR-54 rule), `nextAccountNeedingBalance`, `describeUnlinked`/`describeExclusions`/`describeDiscrepancyCount`, `balanceErrorMessage` over all 18 API error codes (a `Record` that fails to compile if a code is left unworded). |
| Chart data | `src/lib/balanceChart.ts` | `rankSeriesAccounts` (by last absolute SGD value), `buildBalanceLines` (combined + 7 largest + "Other accounts (N)"), `chartLabels`, `summarizeSeries`. |
| Dialogs | `src/components/balances/{DialogFrame,RenameDialog,ChangeTypeDialog,BalanceDialog,MergeDialog}.tsx` | The shared modal frame, and the four account actions: rename, change type (with consequence text), set/replace balance (end-of-day wording, the previous value shown, client validation, Save and next account), merge (same-currency candidates, a worded preview, the balance-choice radios with nothing preselected). |
| Lookup, table, chart, warnings, accounts | `src/components/balances/{BalanceLookup,BalancesTable,IngestedThrough,BalanceChart,DiscrepancyPanel,AccountsSection,BalancesTab}.tsx`, `queries.ts` | Composed in `BalancesTab`, the Dashboard's fifth tab; `queries.ts` holds the shared query keys and the "every write refreshes everything" and "one write at a time" rules. |
| Wiring | `src/pages/DashboardPage.tsx` (fifth tab; From/To hidden on Balances; tab strip scrolls sideways), `src/pages/SettingsPage.tsx` (+`"Balances"` to `CATEGORY_ORDER`) | No new route; `NavBar` is unchanged (no badge, by the user's choice at Functional Design). |
| Contract guard | `api-service/tests/test_contract_fixtures.py` (+11 fixture files), `frontend/tests/contract.test.ts` | One API test builds a scenario and compares real responses with committed JSON; the Frontend checks its own types against the same files. A drift on either side fails a test — this is what would have caught the `start`/`end` mistake. |
| e2e seed and scenario | `database/src/transactagent_db/seed_e2e_fixtures.py` (+3 accounts), `frontend/e2e/balances.spec.ts`, a one-line fix to `frontend/e2e/dashboard.spec.ts` | Added at the user's choice when approving the Code Generation plan. |

## How it was tested

**651 Frontend tests pass** (327 existing + 324 new), run twice with no order dependence; `tsc -b` clean; `eslint .` unchanged at its 5 pre-existing warnings, 0 errors; `vite build` succeeds (642 kB minified, +44 kB over the 598 kB baseline; the "chunk larger than 500 kB" warning is pre-existing, confirmed against the unmodified tree). The 327 existing tests pass unchanged.

**Properties checked** (fast-check, shared generators in `tests/balanceArbitraries.ts`): money round-trips (`parseAmountInput(formatAmount(x)) == x`, `toCents`/`fromCents`), exact addition (commutative, associative, inverse, a list sum independent of order), the chart's ranking (a total order independent of input order, agreeing with an independent sort written separately) and its fold (every account placed exactly once, a gap never becomes a number, the folded line is the exact sum of its known members), `dayBefore` undoing `addDays`.

**Contract fidelity**: `tests/contract.test.ts` checks every Epic 13 DTO's key set, at every nesting level, against `Record<keyof Type, true>` maps (so an unmapped field is a compile error), and separately asserts every amount is a two-place string and every date is `YYYY-MM-DD`, over real API responses.

**Mutation check**: 25 deliberate defects, one at a time, reverted before the next. **25 of 25 caught.** Two were replaced after an honest first run found them poorly chosen: a `MergeDialog` initial-state mutation that the component's own reset-on-selection made unreachable in any test (replaced by a mutation of the radio's `checked` logic, which was caught), and a quiet-retry error-flash mutation whose effect is real in a browser (it prevents one frame of the error showing between React's paint and its effect running) but not observable through React Testing Library's batching (replaced by a mutation of the retry's stop condition — does it ever stop — which is the more important property and was caught).

**Browser check** (Step 15, `construction/plans/frontend-account-balance-code-generation-plan.md` has the full account): a scratch PostgreSQL, the real API, and the built frontend were run on free ports — the live database and the running containers were never touched — and seeded with 20 accounts covering every state the design describes (anchored and unanchored, a missing-transaction discrepancy, two same-named accounts sharing a statement, foreign currency with and without a cached rate, credit cards). Checked in the built-in browser in dark mode, light mode, and at 375px phone width (no horizontal page scroll, matching the Playwright assertion). No defects found.

**End to end** (Step 14): `balances.spec.ts`, seeded by the extended `seed_e2e_fixtures.py` (idempotent, including over a database seeded before the accounts existed, 5 new database tests), run against the real nightly workflow dispatched on this branch — [run 39107017262](https://github.com/jax79sg/transactAgent/actions/runs/39107017262). All 6 new cases and the fixed Dashboard case passed; only the pre-existing Settings/Transactions spec-drift failures occurred (unrelated to this feature; offered to the user as a separate task, not fixed here).

## Amendment: issue #57, "Balance cannot be set again" (2026-10-25)

The owner could not change a balance once it was set. The API always allowed it (`PUT /accounts/{id}/anchor` is an upsert), but the approved design offered the way back only in the Accounts list and opened the dialog empty with a carried-over date. Changed: a **Change balance** button on every balances-table row that has a balance; the dialog starts with the current amount (selected) and date when changing; "Replace balance" became "Change balance" (dialog title "Change the balance of", button "Save change"). Files: `BalancesTable.tsx`, `BalanceDialog.tsx`, `AccountsSection.tsx`; six new unit cases and one e2e case. Not added: deleting a balance, or more than one balance per account.

## Deviations from the design, found while building

- The "Currently replacing" line in `BalanceDialog` does not state when the previous balance was *entered* (only the date it applies to) — that timestamp would need a time zone decision the design did not make, so it was left out.
- `BalancesTable`'s `fx_unavailable` row shows the account's own-currency balance (see the contract correction above); the written design had said no figures at all for that status.
- The Dashboard's three older chart tabs are memoised by their filter (`useMemo`) — found necessary because making the active tab page state re-renders the outgoing tab on every switch, and `react-chartjs-2` calls `update()` on any re-render, which fails in a test environment with no real canvas. This restores the exact behaviour the three existing tests already relied on.

## Not done here

Clicking a chart point to look that date up, a Playwright spec for anything beyond the one Balances scenario added, repairing the pre-existing Settings/Transactions e2e spec drift (flagged separately), the API image rebuild and the frontend image rebuild (both happen at deployment, after Build and Test), and the user guide (a release step).
