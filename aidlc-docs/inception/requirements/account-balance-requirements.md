# Account Balance at a Point in Time — Requirements

## Intent Analysis Summary

- **User Request**: "I would like to add a new feature that is able to determine the balance of my accounts in a particular time."
- **Request Type**: New Feature
- **Scope Estimate**: Multiple Components, all four units touched:
  - **Database**: new `Account` entity, a manual-anchor entity, new `BankStatement` columns, and a one-time wipe-and-reingest backfill.
  - **Ingestion Worker Service**: extraction schema and prompt extended to read an account identifier, an account type, and the printed closing balance; account resolution at ingestion.
  - **API Service**: account management, anchor management, and balance/trend endpoints.
  - **Frontend SPA**: a new balance section on the Dashboard plus account management and anchor entry UI.
- **Complexity Estimate**: Complex. The data model has no concept of an account or an absolute balance today, the extraction contract changes, and the backfill is a destructive operation against live production data.
- **Requirements Depth**: Comprehensive. A cross-unit data-model change plus a destructive backfill on live data warrants full traceability.
- **Extension Configuration (carried over unchanged from `aidlc-state.md`)**: Security Baseline = No, Resiliency Baseline = No, Property-Based Testing = Partial (pure functions and serialization round-trips only). The balance computation (FR-AB-7) is a pure function and falls within the Partial PBT scope.

## Findings That Shaped These Requirements

Established by inspecting the code and live data before asking questions:

1. **No Account entity exists.** Only a free-text `bank_name` is stored per statement and per transaction, already fragmented in live data (e.g. `OCBC`/`OCBC Bank`, `DBS`/`POSB`/`DBS / POSB`, `Trust`/`Trust Bank`/`Trust Bank Singapore Limited`).
2. **No balance has ever been stored.** The extraction prompt (`extraction/prompts.py`) deliberately discards every opening/closing/brought-forward balance line so they are not double-counted as transactions.
3. **Extraction captures no account identifier and no account type.** `RawExtractedStatement` (`extraction/schemas.py`) holds only `bank_name`, `currency`, `confidence`, `statement_date`, and transactions; the prompt reads "bank or credit card" statements indiscriminately.
4. **Statements cannot simply be re-run.** Duplicate detection skips any PDF whose content hash already exists (`uq_bank_statements_pdf_content_hash`), so existing statements must be deleted before reingest. Deleting a statement's transactions also deletes the rows that reference them: `recategorization_jobs`, `recategorization_proposals`, `categorization_disagreements`, and `recurring_payment_matches`.

## Functional Requirements

### Accounts

- **FR-AB-1**: The system shall introduce a first-class `Account` entity. Every account section of an ingested `BankStatement` shall belong to exactly one `Account`; a statement may hold several accounts (amended 2026-10-03, see "Scope Change" below).
- **FR-AB-2**: Accounts shall be auto-created at ingestion from the statement header: bank name plus an account identifier (the account number, or its last few digits) newly extracted from the PDF. Two statements resolving to the same (bank, identifier) pair belong to the same account.
  - **Refinement (2026-10-02, Database Functional Design)**: the matching key is (normalized bank name, account identifier, **currency**), and every key an account has ever been recognized by is kept, so a merge (FR-AB-3) also applies to future statements. The identifier is stored **as printed** on the statement, normalized only for spacing and hyphens (Question 1 = B): the full number when the statement prints it in full, a masked one when it prints it masked.
- **FR-AB-3**: The user shall be able to rename an account, merge two accounts, and correct an account's type in the UI. A merge reassigns the absorbed account's statements to the surviving account and carries over nothing else silently: if both accounts have a manual anchor (FR-AB-6), the user chooses which one survives.
- **FR-AB-4**: Extraction shall read an account type from each statement, as one of: deposit account (savings or current), credit card, or unknown/other. Only deposit accounts participate in the balance feature. Credit-card statements (and any other non-deposit type) continue to be ingested exactly as today for spending and categorization and are excluded only from balances.

### Balance data capture

- **FR-AB-5**: Extraction shall additionally read the printed closing balance of **each account a statement holds** and the date it applies to, stored on that account's **statement-account row** (not on the `BankStatement` itself, and never as a transaction; amended 2026-10-03, see "Scope Change" below). The existing rule that balance-restatement lines must never become transactions is unchanged; the closing balance is read into a separate field, and the code-level safety net in `extraction/service.py` that drops such lines from `transactions` stays in force.
- **FR-AB-6**: For each deposit account the user shall be able to enter, edit, and replace a manual balance anchor: a known real balance as of a specific date (taken from a statement or online banking). The anchor is the primary basis of every balance computation.

### Balance computation

- **FR-AB-7**: The balance of an account as of end-of-day on date D shall be computed in the account's own currency from its anchor (balance A on anchor date T) and the account's transactions:
  - if D is on or after T: A + (inflows − outflows) for transactions dated after T up to and including D;
  - if D is before T: A − (inflows − outflows) for transactions dated after D up to and including T.
  Amounts use the original (account-currency) flows, not the converted SGD amounts.
- **FR-AB-8**: Each captured closing balance (FR-AB-5), one per account section of a statement, shall be used as a cross-check against the anchor-based computation (FR-AB-7) for that account on that closing date. A mismatch shall be surfaced to the user as a visible discrepancy warning identifying the account, the statement, and the size of the difference. It shall not block the feature or silently change any balance. (Assumption: see A-4.)
- **FR-AB-9**: All balances shown, per account and combined, are in SGD. A balance computed in a non-SGD account currency is converted to SGD at the FX rate for the requested date (not the transaction dates' rates). If no usable rate exists for that date, the account's balance is shown as unavailable and excluded from the combined total, with the exclusion made visible, consistent with the existing "conversion unavailable" concept for transactions.
  - **Refinement (2026-10-02, Application Design Question 1 = A)**: the rate is looked up **cache-only** from the existing `fx_rate_cache`, using the nearest *earlier* cached rate for that currency pair on or before the requested date. When that rate's date differs from the requested date, the converted figure is marked **approximate** (mirroring the existing `conversion_is_approximate` concept for transactions). When no such cached rate exists at all, the balance is unavailable as stated above. Consequence: `fx_rate_cache` is populated only by the Ingestion Worker, and only for dates of foreign-currency transactions that needed converting, so a foreign-currency account can show approximate or unavailable balances for dates far from any cached rate. SGD accounts are unaffected.

### Presentation

- **FR-AB-10**: The user shall be able to look up balances for an exact calendar date (end-of-day) and via a month shortcut (end of the selected month). For the current, still-in-progress month the shortcut resolves to today. (Assumption: see A-5.)
- **FR-AB-11**: The lookup shall show a balance per deposit account plus an all-accounts-combined total. An account without an anchor shall appear with a clear "anchor required" prompt and be excluded from the combined total, with that exclusion stated alongside the total.
- **FR-AB-12**: The feature shall also provide a balance-over-time chart for a selectable date range, showing the combined balance and per-account balances. Point granularity (daily vs month-end) is a Functional Design decision.
- **FR-AB-13**: The balance lookup, chart, discrepancy warnings, and entry points to account management and anchor entry live on the existing Dashboard page, not on a new page.
- **FR-AB-14**: The balance view shall state the date through which transactions have been ingested (the latest ingested transaction date), so a balance requested after that date is not mistaken for a live bank balance.

### Backfill (one-time reingest)

- **FR-AB-15**: A one-time backfill shall wipe existing statements and transactions and reingest every PDF from scratch through the normal ingestion pipeline, so every statement gains an account, an account type, and a closing balance.
- **FR-AB-16**: Before the wipe, the user's manual category corrections (transactions with `category_source = manual`) shall be captured, and after reingest re-applied by matching on statement (content hash), transaction date, amount, and description. Matching is best-effort: every correction that could not be matched shall be reported to the user, none dropped silently.
- **FR-AB-17**: Rows that depend on wiped transactions and are not restored by FR-AB-16 (`recategorization_jobs`, `recategorization_proposals`, `categorization_disagreements`, and `recurring_payment_matches`) are discarded with them. Recurring-payment matches are expected to be re-derived by the existing ingestion-time matching; the backfill's completion report shall state how many were re-derived. Everything not dependent on transactions (categories, recurring-payment definitions, users, settings, OAuth credentials, FX rate cache) is preserved.

## Non-Functional Requirements

- **NFR-AB-1 (Exact arithmetic)**: All balance arithmetic uses exact decimal types end to end (no floating point), matching the existing `MONEY` column type. Results are exact to the cent.
- **NFR-AB-2 (Destructive-operation safety)**: The backfill runs only after (a) a verified backup of the affected data exists and its location is reported, (b) a dry-run report states how many statements, transactions, manual corrections, and dependent rows would be affected, and (c) the user explicitly confirms. It is never triggered implicitly by a migration, a deploy, or a normal ingestion run.
- **NFR-AB-3 (Extraction regression safety)**: Extending the prompt and schema (including the move to per-account sections, Scope Change 2026-10-03) must not regress existing extraction behavior, **and this must be demonstrated against real statements, not only synthetic ones**: a read-only comparison of the new extraction's results against the previous extraction's on a sample of real PDFs, before any wipe is proposed. The behavior to preserve is: the day/month-swap handling, ambiguous-date correction, balance-line exclusion, future-date drop, and confidence gating (WR-1, WR-2) must behave as before. New fields are optional at the schema level: a statement missing an account identifier, type, or closing balance still ingests (see A-2, A-3).
- **NFR-AB-4 (Testing)**: The balance computation (FR-AB-7) is a pure function and shall have property-based tests covering at least: anchor-date identity (balance at T equals A), forward/backward consistency (computing forward from A to D then backward from D returns A), and additivity across date splits. Account resolution, anchor handling, cross-check, FX conversion, and the correction-preservation matching shall have conventional unit tests.
- **NFR-AB-5 (Performance)**: A balance lookup and a chart render for the current data volume (about 6,000 transactions) shall feel instant (target under 1 second server time) without loading all transactions into application memory per request.
- **NFR-AB-6 (Access control)**: All new endpoints require the same authentication as the existing API.
- **NFR-AB-7 (UI consistency)**: New Dashboard UI and the new chart respect the existing light/dark theme support (including the shared chart theming) and the existing responsive behavior, including mobile.
- **NFR-AB-8 (No regression)**: Existing categorization, recategorization, recurring-payment, dashboard, and export behavior is unchanged for transactions of all account types.

## Documented Assumptions

These were not explicitly decided by the user and are included for review at approval time:

- **A-1 (Account type scope)**: "Savings accounts" is taken to mean deposit accounts, i.e. savings and current accounts. Credit cards and anything else are excluded.
- **A-2 (No account identifier on a statement)**: If a statement prints no recognizable account identifier, it is attached to an auto-created account keyed on the normalized bank name alone, and the user sorts it out with the merge/rename UI (FR-AB-3).
- **A-3 (Unknown account type)**: If the type cannot be determined, the account is treated as non-deposit (excluded from balances) until the user corrects its type (FR-AB-3).
- **A-4 (Cross-check presentation)**: A discrepancy is a warning, not an error. The tolerance (exact-to-the-cent or a small configured rounding allowance) is decided at Functional Design.
- **A-5 (Month shortcut)**: A past month resolves to its last day; the in-progress month resolves to today.
- **A-6 (One currency and one anchor per account)**: An account has a single currency and one active anchor, replaceable by the user. Multiple simultaneous anchors are out of scope. *(Amended 2026-10-03: the original wording also assumed one account per statement and one statement currency; that is dropped — each account section of a statement carries its own currency, and one account number held in several currencies is simply several accounts, one per currency, per the account-key design. Multi-currency balances inside one account remain represented that way, not as one account with several balances.)*
- **A-7 (Anchor currency)**: The anchor is entered in the account's own currency.
- **A-8 (No anchor, no balance)**: An account with no anchor has no balance, even if it has captured closing balances. Closing balances serve as the cross-check only (per the user's answer), not as a fallback source.

## Open Items Deferred to Functional Design

- Chart point granularity (daily vs month-end) and default date range.
- ~~Where the API Service obtains an FX rate for an arbitrary as-of date, and the fallback when the exact date has no rate.~~ Resolved at Application Design (Question 1 = A): cache-only, nearest earlier cached rate, marked approximate, else unavailable. See the refinement under FR-AB-9.
- ~~Whether the backfill is a script, an admin endpoint, or a CLI command.~~ Resolved at Application Design (Question 2 = A): a single command-line tool in the Ingestion Worker's image. **Where the pre-wipe backup is written, and how, remains open** (the existing nightly backup covers only the `transactions` table, and the worker image has no `pg_dump`).
- Cross-check tolerance (A-4).
- ~~Schema shape for the account identifier (stored in full or masked to the last digits).~~ Resolved at Database Functional Design (Question 1 = B): stored as printed, normalized only for spacing and hyphens. See the refinement under FR-AB-2.

## Scope Change (2026-10-03): Several Accounts per PDF

**Source**: Ingestion Worker Functional Design, clarification Question 1 = B ("include it now"), after the cost was stated: it reopens the approved Database design and code, the Application Design, and Epic 13's stories. Clarification Question 2 = D (the user does not know which of their banks send multi-account PDFs; stored data cannot show it, because extraction has so far kept one bank name and one currency per statement and discarded the rest).

**What changes**
- **A statement holds one or more *account sections*.** Each section has its own account identifier, account type, currency, transactions, and (for deposit accounts) closing balance and its date. A single-account PDF is simply a statement with one section.
- **Data**: the three Epic 13 columns planned for `BankStatement` move to a new per-statement-per-account record (`StatementAccount`: statement, account, closing balance, closing balance date); each transaction links to its section, and the schema guarantees a transaction's section belongs to the transaction's own statement.
- **Resolution**: the Account Resolver runs once per section. Two sections of one PDF that resolve to the same account key are the same account and collapse into one section.
- **Merge** (FR-AB-3): refused for two accounts that appear together in any one statement, since a statement listing both proves they are different accounts.
- **Backfill** (FR-AB-15/17): the wipe set gains `statement_accounts`; the completion report lists, per statement, how many account sections it contained, so the user finds out which PDFs are multi-account from real results.
- **Extraction safeguards** apply per section where they depend on a chronological list of transactions (ambiguous-date correction), and across the whole document where they do not (day/month swap detection, future-date drop, balance-line exclusion, statement-date validation, confidence gating). A model reply that omits sections and returns one flat transaction list is accepted and treated as a single section.
- **Not changed**: A-1..A-5, A-7, A-8; the anchor, the FX behavior, the cross-check's role, Questions 3 to 6 of Round 1, and Round 2's answers all stand.

**Risk accepted by the user**: the extraction prompt and parsing become more complex in the area where this project has had real date-misread incidents (NFR-AB-3, now stated to require a real-statement comparison). Whether any PDF is actually multi-account is not yet known.

## Answers to Clarifying Questions (source of truth)

### Round 1: `account-balance-questions.md`

| # | Question (short) | Answer |
|---|---|---|
| 1 | Account identity | A: introduce a proper `Account` entity; willing to reingest all statements; balances limited to savings accounts, not credit |
| 2 | How balance is computed | Self-referential, no option named ("Answered in Question 2, i am willing to reingest all statements"); resolved in Round 2 Q1 |
| 3 | Time granularity | C: exact date and month shortcut |
| 4 | Scope | B: per-account plus all-accounts combined total |
| 5 | Trend vs point-in-time | B: point-in-time lookup plus balance-over-time chart |
| 6 | Placement | B: existing Dashboard page |

### Round 2: `account-balance-clarification-questions.md`

| # | Question (short) | Answer |
|---|---|---|
| 1 | Balance computation approach | C: manual anchor and captured statement closing balances; per the user, closing balance serves as a cross-check of the manual anchor |
| 2 | Account list establishment | A: auto-create from statement header (bank plus newly extracted account identifier) with rename/merge UI |
| 3 | Savings vs credit determination | A: extend extraction to read account type from the statement; credit excluded automatically. Rationale given: credit transactions are future spending paid from a real savings account later, and including them would confuse the balance view |
| 4 | Currency handling | B: all balances in SGD, converted using the FX rate for the requested date |
| 5 | Backfill approach | B: wipe and reingest, first capturing manual category corrections and re-applying them best-effort, reporting any that cannot be matched |

### Later design-stage answers that changed or settled requirements

| Where | Question (short) | Answer |
|---|---|---|
| Application Design Q1 | FX as-of-date source | A: cache-only, nearest earlier rate, marked approximate (refinement under FR-AB-9) |
| Application Design Q2 | Where the backfill lives | A: a single command-line tool in the Ingestion Worker image |
| Database FD Q1 | Account identifier storage | B: as printed, normalized only for spacing and hyphens (refinement under FR-AB-2) |
| Ingestion Worker FD Q2 | Backfill backup mechanism | A: Python export of every table the wipe touches to a timestamped Drive subfolder, verified by read-back and re-count, with a `restore` command |
| Ingestion Worker FD Q3 | Non-manual categories during the reingest | A: recategorized freshly by the pipeline; only the manual corrections are preserved, so those categories may differ from today's |
| Ingestion Worker FD clarification Q1 | Multi-account PDFs | B: handle them now (Scope Change above) |
| Ingestion Worker FD clarification Q2 | How widespread | D: not sure; the backfill report will show per-statement section counts |

## Summary

Add a balance-at-a-point-in-time feature for the user's savings (deposit) accounts. Accounts become a real entity, auto-created from each statement's header with rename/merge/type-correction in the UI. The user supplies one manual balance anchor per account; balances for any date are computed from that anchor and the account's transactions, in SGD, with each statement's printed closing balance (newly captured) cross-checking the result and raising a visible warning on mismatch. The Dashboard gains a date/month lookup showing per-account and combined balances plus a balance-over-time chart. Credit-card statements keep ingesting as before but never appear in balances. Getting there requires a one-time, safety-gated wipe-and-reingest of all existing statements, preserving manual category corrections on a best-effort, fully reported basis.
