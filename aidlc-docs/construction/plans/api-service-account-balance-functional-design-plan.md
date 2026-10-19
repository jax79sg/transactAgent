# Functional Design Plan — API Service, Epic 13 (Account Balance at a Point in Time)

**Unit**: API Service (the account-management and balance endpoints; no UI, no storage of anything computed)
**Resumes**: the Epic 13 construction loop, whose approved order was Database → {Ingestion Worker, API Service} → Frontend. Database and Ingestion Worker are built; this unit and the Frontend were never started (see the 2026-10-18 correction in `aidlc-state.md`).
**Date**: 2026-10-18
**Triggered by**: the user's "The balance can be filled at runtime, with a date and balance for each account. Then the balance per date for the past can be worked backwards. Also continue the ai-dlc the missing parts."

## Context loaded (Session Continuity)

`account-balance-requirements.md` (FR-AB-1..17, NFR-AB-1..8, A-1..A-8, Scope Change 2026-10-03), `account-balance-stories.md` (US-13.1..13.7), Application Design (`components.md` Account Management and Balance components, `component-methods.md`, `services.md`), Database functional design (`Account`, `AccountKey`, `BalanceAnchor`, `StatementAccount`, `Transaction.statement_account_id`), the existing API Service records (`functional-design/*`, rules up to AR-50) and source layout (one folder per feature: `router.py`, `service.py`, `repository.py`, `schemas.py`), and the live data (read-only).

## Your message, read against the approved requirements

"A date and balance for each account, entered at runtime; past balances worked backwards" is **already FR-AB-6 and FR-AB-7**: one manual anchor per deposit account, entered in the UI, and the balance on any other date is the anchor adjusted by the net flows between the two dates (backwards before the anchor date, forwards after it). **No requirement changes.** The same formula also works forwards, which is how the balance after the anchor date is found.

## Already settled by approved artifacts (not asked again)

| Decision | Source |
|---|---|
| One anchor per account, replaceable; entered in the account's own currency; a future as-of date or a non-number is rejected; none offered for non-deposit accounts | FR-AB-6, A-6, A-7, US-13.3 |
| Balance on date D = anchor ± net flows between D and the anchor date; exact decimals; native currency first | FR-AB-7, NFR-AB-1 |
| All balances shown in SGD, converted at the FX rate for the requested date, cache-only, nearest earlier rate, marked approximate, else unavailable and excluded from the total with the exclusion named | FR-AB-9, Application Design Q1 = A |
| Month shortcut: last day of a past month, today for the current month | FR-AB-10, A-5 |
| No anchor, no balance, even if closing balances exist; the account is listed as "anchor required" and left out of the total | FR-AB-11, A-8 |
| The view states the date through which transactions are ingested | FR-AB-14 |
| Rename, retype, merge; merge refused for different currencies, for accounts that appear together in one statement, and when both have an anchor and none is chosen; a merge also re-points the account's keys | FR-AB-3, US-13.2, BR-35 |
| Nothing computed is stored; everything is computed on request, under 1 second for ~6,000 transactions | Application Design, NFR-AB-5 |
| Same authentication as every other endpoint; the pure balance function is a property-based-testing target | NFR-AB-6, NFR-AB-4 |
| Extensions: Security Baseline = No and Resiliency Baseline = No (skipped, logged); Property-Based Testing = Partial (pure functions only) | `aidlc-state.md` Extension Configuration |

## What the live data says (read-only, 2026-10-18)

These are the facts behind the questions below.

1. **Accounts**: 14 deposit and 6 credit-card accounts, all in SGD. The list needs the tidy-up the UI is for: two accounts are both named "GXS Bank cket" (31 transactions each), "DBS 6220" and "DBS / POSB 6220" look like one account, and "MariBank 8101" has 6 statements but no transactions. No anchor exists yet (`balance_anchors` is empty).
2. **Statement closing balances reconcile with the transactions only partly.** For each deposit account I compared the change between two consecutive printed closing balances with the net of the transactions dated between them: **85 of 113 intervals (75%) match to the cent**. By account: Trust 19 of 19, MariBank 8101 5 of 5, CIMB 5245 8 of 8, UOB 18 of 19, CIMB 4824 10 of 11, MariBank 1090 10 of 13, but **GXS 8782 only 6 of 18 and OCBC 3001 only 8 of 19**. Apart from the two small ones in point 4, the gaps are large (up to about SGD 25,000 for GXS) and not rounding: whenever one month's transactions are incomplete or mis-dated, every balance computed across it from a single anchor is off by that amount.
3. **99 transactions are not linked to any account**: one GXS Bank statement for July 2026 predates the account backfill. They can never be part of a balance until they are attached.
4. **Of the 28 intervals that do not reconcile, only 2 are small**: SGD 0.15 and SGD 0.16 (both GXS, interest months, probably rounding). The other 26 are SGD 1 or more: 7 between 1 and 10, 3 between 10 and 100, and 16 over 100.

## Plan (checklist)

- [x] 1. Analyze the unit context and load the approved artifacts (above).
- [x] 2. Read the live data to ground the open decisions (above).
- [x] 3. Generate the questions below.
- [x] 4. **Collect and analyze the answers**: all seven answered by selecting a listed option, none vague, so no follow-up questions. Question 5 amends two approved requirements, which are amended in place and listed for approval.
- [x] 5. Update `functional-design/business-logic-model.md` in place with a dated Epic 13 addendum: the account-management flows (list, rename, retype, merge, set/replace anchor) and the balance flows (lookup by date or month, series, discrepancies), including the pure balance function and the order of operations for a lookup.
- [x] 6. Update `functional-design/business-rules.md` with rules AR-51 onward: validation (anchor value and date, account type), merge preconditions and atomicity, the balance rules, exclusions and their wording, FX handling, discrepancy rules and tolerance, error codes, and what each endpoint refuses.
- [x] 7. Update `functional-design/domain-entities.md` with the request and response shapes (account summary, anchor, balances result, series, discrepancy) and the endpoint list with paths, methods and status codes.
- [x] 8. Traceability check: every FR-AB, NFR-AB and US-13.x that the API carries (US-13.2 to US-13.6) maps to a named rule.
- [ ] 9. Present the Functional Design completion message and **wait for your explicit approval** (Request Changes / Continue to Code Generation). *(Presented 2026-10-18; awaiting approval.)* NFR Requirements, NFR Design and Infrastructure Design stay skipped per the approved execution plan.

## Questions

Please fill in the letter after each `[Answer]:`. If none fits, choose the last option and describe it.

> **Answered interactively in chat on 2026-10-18** (the user has no terminal access to edit this file). Each answer below was copied here by the assistant from the user's selection; every one was the option marked Recommended.

### Question 1: Chart points
What does the balance-over-time chart plot? (Every point must equal what a single-date lookup returns for that day, whichever you pick.)

A) Every day in the range (smooth line; up to about 670 points per account for the full history)

B) The last day of each month only (about 22 points for the full history; coarse but light)

C) Automatic: every day when the range is 3 months or shorter, month-end points for longer ranges

D) The user chooses daily or month-end on the chart, starting from automatic (C)

E) Other (please describe after [Answer]: tag below)

[Answer]: D) The user chooses daily or month-end on the chart, starting from automatic (C). *(Answered in chat 2026-10-18: "Automatic + your toggle".)*

### Question 2: Chart default range
Which date range does the chart show when you first open the Dashboard?

A) The last 12 months

B) The last 3 months

C) All history (from the earliest transaction)

D) Since the oldest anchor date

E) Other (please describe after [Answer]: tag below)

[Answer]: A) The last 12 months. *(Answered in chat 2026-10-18.)*

### Question 3: Mismatch tolerance (A-4)
When does a printed closing balance disagree with the computed one? In today's data only 2 of the 28 mismatching intervals are under SGD 1 (SGD 0.15 and 0.16, both GXS interest months); the other 26 are SGD 1 or more, so an allowance of SGD 1.00 would hide just those two.

A) Any difference of one cent or more (exact)

B) Differences up to SGD 1.00 are ignored

C) A Settings value (default exact), changeable without a release

D) Other (please describe after [Answer]: tag below)

[Answer]: C) A Settings value (default exact), changeable without a release. *(Answered in chat 2026-10-18: "Settings value, default exact".)*

### Question 4: How a discrepancy is reported (FR-AB-8, US-13.6)
Requirement FR-AB-8 compares each printed closing balance with the balance computed from your anchor on that date. Because the computed figure is cumulative, **one month with missing transactions makes every statement on one side of it show a discrepancy of the same size**, which hides where the real problem is (e.g. GXS shows gaps in 12 of 18 intervals).

A) Exactly as FR-AB-8 reads: per statement, printed closing balance versus the balance computed from the anchor

B) Per statement period: the change between two consecutive printed closing balances versus the transactions between them, which points at the month that is wrong and does not depend on the anchor

C) Both: the per-statement difference required by FR-AB-8, plus the per-period gap marking where it started

D) Other (please describe after [Answer]: tag below)

[Answer]: C) Both: the per-statement difference required by FR-AB-8, plus the per-period gap marking where it started. *(Answered in chat 2026-10-18: "Both views".)*

### Question 5: Can statement closing balances also set the balance? (changes an approved decision)
You decided earlier that closing balances are only a cross-check and the manual anchor is the sole basis (Round 2 Q1 = C, assumption A-8). The reconciliation above shows a single anchor will give visibly wrong balances across any month with incomplete transactions (GXS and OCBC especially). This is the one question that would amend the approved requirements (FR-AB-7, A-8), so it needs your explicit choice.

A) Keep the approved rule: one manual anchor per account; closing balances only cross-check it

B) Use the nearest known balance for each date: the manual anchor or a printed closing balance, whichever is closest. Balances then match the statement on every statement date and an error in one month no longer shifts the others. The manual anchor is still required to switch an account on, and discrepancies are still reported (requirements FR-AB-7 and A-8 would be amended)

C) Keep the approved rule, but mark any balance computed across a month with a known mismatch as "uncertain" in the lookup and chart (numbers unchanged)

D) Other (please describe after [Answer]: tag below)

[Answer]: B) Use the nearest known balance for each date: the manual anchor or a printed closing balance, whichever is closest. Balances then match the statement on every statement date and an error in one month no longer shifts the others. The manual anchor is still required to switch an account on, and discrepancies are still reported (requirements FR-AB-7 and A-8 are amended). *(Answered in chat 2026-10-18: "Nearest known balance".)*

### Question 6: Transactions that belong to no account
99 transactions (one GXS Bank statement, July 2026) are not linked to any account, so no balance can include them. What should the balance view do?

A) Say so: show a notice with the count, bank, date range and net amount, and leave them out of every balance

B) Say so, and let me attach such a statement's transactions to one of my accounts from the same screen

C) Guess: attach them to the account that has the same bank and currency

D) Other (please describe after [Answer]: tag below)

[Answer]: A) Say so: show a notice with the count, bank, date range and net amount, and leave them out of every balance. *(Answered in chat 2026-10-18: "Show a notice".)*

### Question 7: What is "today"?
"Today" decides the month shortcut for the current month, and whether an anchor date is "in the future". The existing Dashboard uses the server's UTC day, which is a day behind Singapore between 00:00 and 08:00.

A) The server's UTC date, like the rest of the app

B) The Singapore date (Asia/Singapore), fixed

C) The date of the browser making the request, sent with the request

D) A Settings value for the reporting time zone, defaulting to Asia/Singapore

E) Other (please describe after [Answer]: tag below)

[Answer]: D) A Settings value for the reporting time zone, defaulting to Asia/Singapore. *(Answered in chat 2026-10-18: "Setting, default Singapore".)*


## Traceability (step 8)

| Requirement or story | Where it is designed (`business-rules.md`) |
|---|---|
| US-13.2 (rename, merge, retype) / FR-AB-3 | AR-51, AR-52, AR-54, AR-65 |
| US-13.3 (anchor) / FR-AB-6 | AR-53, AR-57, AR-64 |
| US-13.4 (lookup) / FR-AB-7, 9, 10, 11, 14 | AR-55, AR-56, AR-57, AR-58, AR-59, AR-60 |
| US-13.5 (chart) / FR-AB-12 | AR-61 (with AR-55, AR-56, AR-59) |
| US-13.6 (discrepancy) / FR-AB-8, A-4 | AR-62, AR-63 |
| NFR-AB-1 exact arithmetic | AR-56, AR-59 |
| NFR-AB-4 property-based tests | AR-56 (the properties), checked at Code Generation |
| NFR-AB-5 performance | AR-66 |
| NFR-AB-6 access control, NFR-AB-8 no regression | AR-67 |
| FR-AB-13 Dashboard placement, NFR-AB-7 theming and mobile | Frontend unit |
| Already built, not this unit | US-13.1, US-13.7, FR-AB-1, 2, 4, 5, 15-17, NFR-AB-2, 3 (Database and Ingestion Worker) |

Every API-carried requirement maps to a rule; nothing is left to be invented at Code Generation except the SQL and the framework wiring.

## Carried to Code Generation (found while designing)

- Settings entries take effect on API restart (AR-63), as the other API-owned entries do; confirm the catalog's entry count and the Settings page text at that stage.
- `zoneinfo` is already used by the Costs endpoint; confirm in the API image that the reporting time zone resolves (no extra dependency expected).
- The balance function is the property-based-testing target (Partial extension): `.aidlc-rule-details/extensions/testing/property-based/` is loaded at that stage.
