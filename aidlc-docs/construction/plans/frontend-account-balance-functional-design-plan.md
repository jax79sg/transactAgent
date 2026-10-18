# Functional Design Plan — Frontend SPA, Epic 13 (Account Balance at a Point in Time)

**Unit**: Frontend SPA (the Balances screens on the Dashboard: lookup, chart, discrepancies, account management, balance entry, and the Settings entries). No new page, no new route, no storage of anything computed.
**Follows**: the API Service unit of Epic 13, approved 2026-10-18 ("Approve"). Its seven endpoints and DTOs are fixed in `construction/api-service/functional-design/domain-entities.md`; this unit is built to that contract and changes nothing in it.
**Date**: 2026-10-18
**Triggered by**: the user's "Approve" on the API Service Code Generation stage, continuing "Also continue the ai-dlc the missing parts."

## Context loaded (Session Continuity)

`account-balance-requirements.md` (FR-AB-1..17, NFR-AB-1..8, A-1..A-8, Scope Change 2026-10-03, Amendment 2026-10-18), `account-balance-stories.md` (US-13.2..13.6 are this unit's), the API Service design (`business-rules.md` AR-51..AR-67, `domain-entities.md` Epic 13 section) and its built code summary, the existing Frontend design (`frontend-components.md`, `business-logic-model.md` through Epic 14) and source (`DashboardPage.tsx`, `NavBar.tsx`, `SettingsPage.tsx`, `api/client.ts`, `api/types.ts`, `lib/chart*.ts`, the test and Playwright conventions), and the live data (read-only, as recorded in the API plan).

## Already settled by approved artifacts (not asked again)

| Decision | Source |
|---|---|
| The balance lookup, chart, discrepancy warnings and the entry points to account management and anchor entry live on the **existing Dashboard page**, not on a new page | FR-AB-13 |
| A lookup by exact date or by month; a past month means its last day, the current month means today; a date after today is refused | FR-AB-10, A-5, AR-57 |
| One row per deposit account plus a combined total in SGD; an account with no anchor shows "anchor required" with a way to enter it, and the exclusion is stated beside the total; credit cards and unknown types never appear | FR-AB-11, US-13.3, US-13.4 |
| The date through which transactions are ingested is shown on every lookup; every figure says what it was worked from (anchor, or a statement closing balance and its date) | FR-AB-14, AR-55, AR-58 |
| A foreign-currency figure shows its own currency and the SGD value, marked approximate when the rate is not for the exact date, and "unavailable" (left out of the total, with the reason) when no rate exists | FR-AB-9, AR-59 |
| A notice for transactions linked to no account (count, banks, dates, net per currency); information only, no action | Q6 = A, AR-60 |
| The chart: combined balance and per-account balances; opens on the last 12 months; automatic daily/month-end with a toggle; a missing foreign-currency rate is a gap, never a guess; accounts that cannot be plotted are named with the reason; every plotted point equals the lookup for that date | FR-AB-12, Q1 = D, Q2 = A, US-13.5, AR-61 |
| Balance entry: in the account's own currency, stated to be the **end-of-day** balance, the previous value is visible before it is replaced, a non-number or future date is refused with a clear message and nothing is saved, and no entry is offered for a non-deposit account | US-13.3, AR-53 |
| Rename, change type, merge; a merge with two anchors makes the user choose which survives; a merge refused for different currencies or for accounts listed together in one statement is explained | US-13.2, AR-52, AR-54 |
| Discrepancies: two views (per-statement difference and per-period gap), only for accounts with an anchor, naming the account and the statement and the size; a warning never blocks or changes a figure | FR-AB-8, Q3 = C, Q4 = C, US-13.6, AR-62 |
| Light and dark themes (shared chart theming) and the responsive layout, including mobile | NFR-AB-7 |
| Money is a two-place string on the wire and stays a string until displayed; the Frontend keeps its one error-handling path (`{error, message, details}`); a malformed date is a framework 422 | NFR-AB-1, AR-64 |
| Extensions: Security Baseline = No and Resiliency Baseline = No (skipped, logged); Property-Based Testing = Partial (pure functions and round-trips only) | `aidlc-state.md` Extension Configuration |

## What the existing app and the API contract settle for me (not asked; listed so they can be reviewed)

1. **`PATCH` is new to this app.** `apiRequest` only knows GET, POST, PUT and DELETE, and the rename/retype call is a `PATCH`. The method list gains it. The web app and the API are different origins (ports 8787 and 7878), so the browser sends a preflight; the API already allows `PATCH` (added and tested in the API unit), which takes effect when the API image is rebuilt and restarted at deployment.
2. **The page's From/To box belongs to the three older charts.** The Recurring Payments tab already ignores it. A Balances tab with its own range (default last 12 months, Q2 = A) would be misleading under it, so it is hidden while the Balances tab is showing; the other four tabs are untouched.
3. **A lookup needs a date to start from, and the API refuses a future one.** The first lookup uses the browser's local calendar date (not the UTC date the older Dashboard code uses, which is yesterday in Singapore before 08:00). If the API answers `date_in_future` (the browser's clock is ahead of the reporting time zone), the screen retries once with the day before and then follows the `today` the API returns. After that the screen uses the API's `today`, never the browser's.
4. **Settings needs no new screen.** `reporting_time_zone` and `balance_mismatch_tolerance` appear through the existing catalog-driven rendering (category "Balances", owned by the API Service, change takes effect on API restart); "Balances" is added to the page's category order so it is not left at the very end.
5. **No new dependency.** Chart.js already has the line chart and the legend registered; the category axis suffices because the API returns the dates to plot.
6. **Components follow the Epic 14 precedent**: React Query for server state with invalidation after each write, Radix `Dialog` for modals, Tailwind with a `dark:` variant on every element, a `data-testid` on every state and action, one `api/<feature>.ts` module and the DTOs in `api/types.ts`, status always in words as well as colour.

## What the live data says that shapes the screens (read-only, from the API plan)

- 14 deposit and 6 credit-card accounts, all SGD; **no anchor exists yet**, so the first thing the owner sees is 14 "anchor required" rows and the way to fix them must be quick.
- Two accounts are both named "GXS Bank cket" and cannot be merged (one statement lists both); "DBS 6220" and "DBS / POSB 6220" are the same account; "MariBank 8101" has 6 statements and no transactions. The account list must make same-named accounts distinguishable (identifier, statement and transaction counts, latest transaction date).
- **28 of 113** statement intervals do not reconcile with the transactions between them (GXS and OCBC mostly), so once anchors are in, discrepancy findings will be common and a period gap stays until the transactions are fixed. A warning that is loud everywhere would be permanent noise (Question 3).
- 99 July-2026 GXS transactions are linked to no account (the notice will show on every lookup until that statement is re-ingested); transactions are ingested through 2026-09-30 while today is 2026-10-18.

## Plan (checklist)

- [x] 1. Analyze the unit context and load the approved artifacts (above).
- [x] 2. Read the existing Frontend design and source, and the API contract (above).
- [x] 3. Generate the questions below.
- [x] 4. **Collect and analyze the answers**: all five answered by selecting a listed option, none vague, so no follow-up questions.
- [x] 5. Write the Epic 13 sections of `construction/frontend/functional-design/frontend-components.md`: the Balances tab and its parts (lookup, balances table, notices, chart, discrepancies, accounts section, balance dialog, merge dialog), the shared types and API module, the Settings entries.
- [x] 6. Write the Epic 13 sections of `construction/frontend/functional-design/business-logic-model.md`: first-lookup and "today" handling, query keys and invalidation after each write, merge and balance-entry flows, error mapping, display rules (money, basis wording, gaps), responsive/theme/accessibility.
- [x] 7. Write the traceability table (every story criterion of US-13.2 to US-13.6 to a component) and "Carried to Code Generation".
- [ ] 8. Update `aidlc-state.md` and `audit.md`; present the standard completion message; **wait for explicit approval**.

## Questions

Please fill in the letter after each `[Answer]:`. If none fits, choose the last option and describe it.

> **Answered interactively in chat on 2026-10-18** (the user has no terminal access to edit this file). Each answer below was copied here by the assistant from the user's selection; every one was the option marked Recommended.

### Question 1: Where does the balance section sit on the Dashboard? (FR-AB-13 fixes the page, not the layout)
The Dashboard has three charts and a Recurring Payments tab, with one From/To box above them.

A) A **fifth tab, "Balances"**, beside Recurring Payments, with its own date controls (the From/To box is hidden on this tab). The Dashboard still opens on Category Trends, so nothing about today's first screen changes. This is how Recurring Payments was added.

B) The same fifth tab, and the Dashboard **opens on it**.

C) A **section above the tabs**, always visible, with the existing charts pushed below it.

D) Other (please describe after [Answer]: tag below)

[Answer]: A) A **fifth tab, "Balances"**, beside Recurring Payments, own date controls, Dashboard still opens on Category Trends. *(Answered in chat 2026-10-18: "Fifth tab, opens as today (Recommended)".)*

### Question 2: Which lines does the balance chart draw? (FR-AB-12)
With 14 deposit accounts the chart cannot give every account its own colour: the app's chart rule is eight distinct colours at most, with anything beyond folded into one grey "Other" series.

A) The **combined total** (thick line) plus the **7 accounts with the largest balance** on the last day, and everything beyond that folded into one grey **"Other accounts"** line. Clicking a name in the legend hides or shows that line.

B) The **combined total only** at first, with a row of tick boxes to add accounts one at a time (up to 7 at once).

C) **Two charts**: the combined total on its own, and below it the per-account lines (same 7 plus "Other accounts" rule).

D) Other (please describe after [Answer]: tag below)

[Answer]: A) The **combined total** (thick line) plus the **7 accounts with the largest balance** on the last day, the rest folded into one grey **"Other accounts"** line; legend click hides or shows a line. *(Answered in chat 2026-10-18: "Combined + 7 largest + Other (Recommended)".)*

### Question 3: How prominent are discrepancy warnings? (US-13.6)
Once anchors are in, many findings are likely (28 of 113 statement intervals do not reconcile today), and a period gap stays until the missing transactions are fixed. The warning must be visible but must not nag forever.

A) A **one-line summary at the top of the Balances tab** ("4 accounts have differences with their statements"), with a **Show details** control that opens the two views (per statement, per period) for each account. Nothing appears on the other Dashboard tabs.

B) The **full details always open** in the Balances tab, below the balances.

C) The one-line summary on **every Dashboard tab**, with the details in the Balances tab.

D) Other (please describe after [Answer]: tag below)

[Answer]: A) A **one-line summary at the top of the Balances tab** with a **Show details** control; nothing on the other Dashboard tabs. *(Answered in chat 2026-10-18: "Summary line + Show details (Recommended)".)*

### Question 4: Where do rename, change type, merge and balance entry live? (FR-AB-13: entry points on the Dashboard)

A) An **"Accounts" section at the bottom of the Balances tab** listing every account (deposit accounts first, then cards, then unknown), each row with **Set or replace balance**, **Rename**, **Change type** and **Merge into…**, each opening a small dialog. The "anchor required" prompt in the balances table opens the same balance dialog directly.

B) A **"Manage accounts" button** in the Balances tab that opens one large panel containing the same list and actions; the "anchor required" prompt opens the balance dialog directly.

C) Only **balance entry** on the Dashboard (from the "anchor required" prompt and a list); **rename, change type and merge on the Settings page**, with a link from the Dashboard.

D) Other (please describe after [Answer]: tag below)

[Answer]: A) An **"Accounts" section at the bottom of the Balances tab**, each row with Set or replace balance, Rename, Change type and Merge into…, each opening a small dialog; the "anchor required" prompt opens the balance dialog directly. *(Answered in chat 2026-10-18: "Accounts section in the tab (Recommended)".)*

### Question 5: Should the Dashboard link in the top bar show a badge for balances?
The link already carries the Recurring Payments badge, and Review carries two more.

A) **No badge.** The "anchor required" prompts inside the Balances tab are the reminder, and discrepancies are not badge-worthy because many will persist.

B) A badge counting **deposit accounts that still need a balance**, hidden at zero (gone once you have entered them all), in a colour different from the Recurring Payments one.

C) Other (please describe after [Answer]: tag below)

[Answer]: A) **No badge.** *(Answered in chat 2026-10-18: "No badge (Recommended)".)*

## Contract check against the built API (found while designing, 2026-10-18)

The approved `domain-entities.md` was compared field by field with the DTOs the API Service unit actually built (`balances/schemas.py`, `accounts/schemas.py`) and its tests. **Two differences**, both in the document, not the code (the API's tests pin the built shapes):

1. **`SeriesResponse` names its range `start` and `end`**, not `from` and `to` as the document said (`from` cannot be a Python field name). The request query parameters are still `from` and `to`. The Frontend is built to `start` and `end`.
2. **`statementId`, `fromStatementId` and `toStatementId` can be null** in the discrepancy DTOs (the pure module allows a known balance without a statement); the document said they were always present. The Frontend never relies on them being present.

`domain-entities.md` and the "Contract for the Frontend unit" paragraph of `construction/api-service/code/account-balance-summary.md` (which wrongly said the shapes were exactly the document's) are corrected in place and logged in `audit.md`. Everything else matched: `AccountDTO`, `AnchorDTO`, `AnchorResponse`, `MergeRequest`, `AccountBalanceDTO`, `BasisDTO`, `UnlinkedNoticeDTO`, `BalancesResponse`, `SeriesAccountDTO`, `SeriesPointDTO`, `DiscrepanciesResponse`, and the seven paths and query names. This is the kind of mismatch a type-only hand copy of the document cannot catch, so Code Generation should derive its test fixtures from responses the real API produced (see "Carried to Code Generation").

## Traceability (step 7)

| Story and criterion | Where it is designed |
|---|---|
| **US-13.2** rename shows everywhere | RenameDialog; every write invalidates `["accounts"]` and `["balances"]` (Queries) |
| US-13.2 merge, absorbed account gone, balances reflect it | MergeDialog; Merge Flow |
| US-13.2 both anchors: user chooses, none dropped silently | MergeDialog balances radios, none preselected, Merge disabled until chosen |
| US-13.2 currencies differ: refused with explanation | Same-currency candidates only; `merge_currency_mismatch` sentence |
| US-13.2 accounts together in one statement: refused with explanation | `merge_appear_together` sentence, stays in the dialog, suggests renaming |
| US-13.2 retype to deposit / to credit card | ChangeTypeDialog (consequence text both ways); the account then shows "Anchor required" or leaves balances |
| **US-13.3** enter a balance and date | BalanceDialog; Balance Entry Flow |
| US-13.3 own currency, shown with it | BalanceDialog text "In <currency>"; AccountsSection and table show the currency |
| US-13.3 replace, previous value visible before confirming | `balance-previous`; "Replace balance" |
| US-13.3 invalid number or future date rejected, nothing saved | `parseAmountInput` and date check before sending; the API's refusals mapped (Error Mapping) |
| US-13.3 no option for a non-deposit account | Actions only when `canHaveAnchor`; "Not in balances" |
| US-13.3 "anchor required" prompt leads to entry | BalancesTable `set-balance-<id>` opens the dialog |
| US-13.3 end of day stated on the form | BalanceDialog wording |
| **US-13.4** exact date; month shortcut; heading says which | BalanceLookup (Date, Month, Today); heading from the response |
| US-13.4 nearest known balance, "worked from" | BalancesTable "Worked from" column (`describeBasis`) |
| US-13.4 unlinked-transactions notice | UnlinkedNotice |
| US-13.4 date rules, today in the reporting zone | First lookup and "today"; the API's `today` drives every limit; `max` on inputs; error sentences |
| US-13.4 foreign currency, approximate, unavailable and excluded with the reason | BalancesTable row states; `combined-exclusions` |
| US-13.4 no anchor: "anchor required", excluded, stated beside the total | BalancesTable row state and `combined-exclusions` |
| US-13.4 ingested-through on every lookup | IngestedThrough (amber and a jump button when the date is later) |
| US-13.4 exact to the cent, fast | Money stays a string; no floating-point sums (Shared helpers); the API's 16 ms |
| US-13.4 no deposit accounts: explanatory empty state | `balances-empty-state` |
| US-13.4 light/dark, phone and desktop | Responsive, Theme, and Accessibility Rules |
| **US-13.5** chart of combined and per-account balance | BalanceChart; Chart Data Preparation |
| US-13.5 matches the lookup exactly | Both read the API's figures (the API guarantees equality); strings plotted unchanged |
| US-13.5 range spanning the anchor | Nothing to do on the screen; the API works backward; From/To accept any past range |
| US-13.5 excluded accounts named with the reason | `series-not-plotted` from `missingAccounts` |
| US-13.5 missing rate is a gap, not a guess | `null` plotted as a break; note under the chart |
| US-13.5 daily/month-end toggle, automatic default; last 12 months | Points choice and Last 12 months control; no dates sent by default |
| US-13.5 chart theming light/dark | `getChartTheme`; ink colour has both values |
| **US-13.6** mismatch warning naming account, statement and size | DiscrepancyDetails tables (statement named by closing date) |
| US-13.6 no warning when they agree | DiscrepancySummary "statements agree" line; no tables |
| US-13.6 never blocks or alters a figure | Separate query, own failure state; the lookup does not depend on it |
| US-13.6 no anchor: no check, no spurious warning | The API returns only checked accounts; the summary renders nothing when none is checked |
| US-13.6 warning disappears when the anchor is corrected | Every write invalidates `["balances"]` including discrepancies |
| US-13.6 tolerance | Footer states the tolerance with a link to Settings; Settings "Balances" category |
| US-13.6 where it started (period gap) | Second table with the explanation |
| NFR-AB-7 theme and responsive | Rules section; tab strip scroll; list not table for accounts |
| NFR-AB-8 no regression | Other four tabs unchanged except the filter's visibility on Balances; NavBar unchanged |

Every acceptance criterion of US-13.2 to US-13.6 maps to a component above. US-13.1 and US-13.7 are not this unit's.

## Design decisions not asked (for review at approval)

- The month lookup uses two selects (month, year), not the browser's month input, which does not exist in every browser (desktop Safari).
- **Save and next account** in the balance dialog, because 14 accounts need a first balance and the date is usually the same.
- The first lookup uses the browser's local date and retries once with the day before if the API says it is in the future; afterwards the API's `today` is used.
- The page's From/To box is hidden on the Balances tab, and the tab strip scrolls sideways on a phone (a small change to the existing tab list that makes five tabs fit).
- The accounts section is a wrapping list, not a table.
- "Other accounts (N)" is labelled with the number of accounts folded in; with exactly 8 accounts it holds one.
- The merge dialog shows what will happen, including a type change, using the same rule as the API, and says it cannot be undone.
- A one-sentence summary of the chart's start, end and change is written beneath it.
- A statement in the discrepancy tables is named by its closing date, because the API returns no file name.
- Clicking a chart point to look that date up is not included.

## Carried to Code Generation (found while designing)

1. **Add `PATCH`** to `apiRequest`'s method type, with a test. Every API call is cross-origin (web app and API are on different ports), so the preflight must pass: the API already allows `PATCH`, which reaches a running API only after its image is rebuilt and restarted (deployment).
2. **Contract fixtures from the real API.** Generate one JSON response per endpoint (and the error shape) by running the built API against a seeded test database, commit them as `frontend/tests/fixtures/balances/*.json` with the small script that produced them, and have Frontend tests check the DTO types against them (TypeScript `satisfies` plus a runtime key check). This is what would have caught the `start`/`end` mismatch, and closes the "no frontend-to-API contract test" gap recorded for Epic 14. Regenerating them is a documented step.
3. **Property-based tests (fast-check, already a dev dependency)** for the pure helpers: `formatAmount`/`parseAmountInput` round trip, exact-cents addition (associative, commutative, inverse), the chart folding (the folded lines add up to the unfolded total; ranking is a stable total order; no value is created or lost; a null stays null), and `mergeTypeOutcome` against the API's cases. Shared arbitraries in `tests/` (PBT-07); failing seeds are reported by fast-check and a replay recipe is documented (PBT-08); the framework is already declared (PBT-09).
4. **Component tests** per component with the API modules mocked, in the project's style (`vi.mock("../src/api/...")`), asserting by `data-testid` and role; DashboardPage tests updated (five tabs; From/To hidden on Balances; opens on Category Trends); SettingsPage test for the Balances category; `apiClient` test for `PATCH`.
5. **Mutation check** as in the earlier units (deliberate breakages, each must fail a test), including the money helpers, the fold rule, the first-lookup retry, the invalidation after a write, the merge radios, and the dialogs' disabled states.
6. **Look at it in a browser.** After generation, run the built app against a scratch API and database (never the live one) with sample accounts, anchors, mismatches and a foreign-currency account, and check light and dark mode, a phone-width window, the dialogs and the chart in the built-in browser. Epic 14 recorded that nothing was viewed in a browser; this unit should not repeat that.
7. **Playwright**: decide at planning whether to add a Balances scenario (open the tab, see "anchor required", set a balance) and its seed fixtures; check whether the existing `dashboard.spec.ts` case "loads with the recurring payments summary visible" can pass today, since the Recurring Payments tab is not the one that opens. Running Playwright is part of Build and Test.
8. Export `formatDay` from `lib/duplicates.ts` (it is private today) rather than copying the month-name table.
9. **Deployment (not code)**: rebuild and restart the **API** (new endpoints, `PATCH` in CORS, two settings) and rebuild the **frontend** image; no worker change and no migration. The new settings take effect on the API restart.
10. **Documentation**: `aidlc-docs/construction/frontend/code/account-balance-summary.md` and the code README; the user guide is a release step.
