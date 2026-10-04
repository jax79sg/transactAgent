# User Stories — Account Balance at a Point in Time

Appends **Epic 13** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7, `recurring-payments-stories.md` Epic 8, `embedding-similarity-stories.md` Epic 9, `configurable-app-settings-stories.md` Epic 10, `background-process-visibility-stories.md` Epic 11, `dark-mode-stories.md` Epic 12), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`), unchanged. This feature introduces no new persona. The owner is also the person who triggers the one-time backfill (US-13.7), consistent with the persona's existing description as comfortable running `docker-compose` commands.
**Granularity/format**: Coarse, epic-level, Given/When/Then plus edge cases, matching the existing convention.
**Traceability**: Each story references `account-balance-requirements.md`'s FR-AB, NFR-AB, and A-n (documented assumption) IDs. Where an acceptance criterion rests on a documented assumption, it says so, so approving these stories also confirms those assumptions.

---

## Epic 13: Account Balance at a Point in Time

### US-13.1: My accounts are identified automatically, and credit cards stay out of balances
**As** the Account Owner, **I want** every ingested statement attached to the right account automatically, with credit-card statements kept out of the balance view, **so that** I don't set up accounts by hand and my balances reflect only real money in my savings.

**Traces to**: FR-AB-1, FR-AB-2, FR-AB-4, NFR-AB-3, NFR-AB-8, A-1, A-2, A-3

**Acceptance Criteria**:
- *Happy path, new account*: Given a statement from a bank and account identifier I haven't ingested before, When ingestion processes it, Then a new account is created from the bank name plus the account identifier read from the statement, and the statement belongs to that account.
- *Happy path, existing account*: Given an account already exists for a statement's bank and account identifier, When another statement with the same pair is ingested, Then it attaches to the existing account and no duplicate account is created.
- *Two accounts at one bank*: Given two statements from the same bank with different account identifiers, When both are ingested, Then they resolve to two separate accounts.
- *Several accounts in one PDF* (added 2026-10-03, Scope Change): Given a single PDF that holds more than one account (for example a savings and a current account, or a savings account and a credit card), When it is ingested, Then each account section is resolved on its own: it is linked to (or creates) its own account, its transactions belong to that account, and it carries its own account type, currency, and closing balance.
- *Same account twice in one PDF* (added 2026-10-03): Given a PDF in which two sections turn out to be the same account (same bank, same account identifier, same currency), When it is ingested, Then they collapse into one section for that account rather than creating a duplicate or failing.
- *Single-account PDFs unchanged* (added 2026-10-03): Given an ordinary PDF with one account, When it is ingested, Then it behaves as a statement with exactly one section, with no visible difference.
- *Credit card excluded from balances*: Given a credit-card statement, When it is ingested, Then its transactions are ingested and categorized exactly as today, its account is recorded as a credit-card account, and it never appears in any balance lookup, total, or chart.
- *Current accounts count as deposit accounts*: Given a statement from a current account, When it is ingested, Then it is treated as a deposit account and is eligible for balances (A-1).
- *Edge case, no account identifier printed*: Given a statement that prints no recognizable account identifier, When it is ingested, Then it still ingests successfully and is attached to an auto-created account keyed on the normalized bank name alone, which I can later fix with merge/rename (A-2, US-13.2).
- *Edge case, account type cannot be determined*: Given a statement whose account type cannot be determined, When it is ingested, Then it still ingests, and its account is treated as non-deposit and excluded from balances until I correct its type (A-3, US-13.2).
- *No regression*: Given statements ingested after this feature ships, When extraction runs, Then the existing safeguards (day/month correction, balance-line exclusion, future-date drop, confidence gating) behave exactly as before, and the transactions extracted from a given statement are unchanged by the new account/type/balance fields (NFR-AB-3, NFR-AB-8).

### US-13.2: I can tidy up my accounts
**As** the Account Owner, **I want** to rename accounts, merge two that are really one, and correct an account's type **so that** automatic identification mistakes never leave me with a wrong or confusing balance view.

**Traces to**: FR-AB-3, A-3, A-6

**Acceptance Criteria**:
- *Happy path, rename*: Given the list of my accounts, When I rename one, Then the new name appears everywhere that account is shown (lookup, chart, warnings).
- *Happy path, merge*: Given two accounts that are really the same real-world account, When I merge one into the other, Then all of the absorbed account's statements, and the transactions on them, count under the surviving account; the absorbed account no longer appears; and balances reflect the merge.
- *Edge case, both accounts have an anchor*: Given both accounts have a manual anchor (US-13.3), When I merge them, Then I must choose which anchor survives before the merge completes; neither is dropped silently.
- *Edge case, currencies differ*: Given two accounts with different currencies, When I try to merge them, Then the merge is refused with an explanation, since an account has a single currency (A-6).
- *Edge case, accounts that appear together in one statement* (added 2026-10-03, Scope Change): Given two accounts that are both listed in the same statement, When I try to merge them, Then the merge is refused with an explanation: a statement that lists both proves they are different accounts.
- *Happy path, correct the type to deposit*: Given an account classified as credit card or unknown, When I set its type to deposit account, Then it becomes eligible for balances and shows "anchor required" until I set one (US-13.3).
- *Happy path, correct the type to credit card*: Given a deposit account that is really a credit card, When I set its type to credit card, Then it disappears from balances, totals, and charts.

### US-13.3: I can tell the app a known real balance for each savings account
**As** the Account Owner, **I want** to enter a balance I know to be real, as of a specific date, for each savings account **so that** the app has a trustworthy starting point from which to work out my balance on any other date.

**Traces to**: FR-AB-6, A-6, A-7

**Acceptance Criteria**:
- *Happy path*: Given a deposit account with no anchor, When I enter a known balance and the date it applies to, Then it is saved and balances for that account become available.
- *Currency*: Given an account in a non-SGD currency, When I enter its anchor, Then it is entered in that account's own currency and shown with that currency (A-7).
- *Replace*: Given an account already has an anchor, When I enter a new one, Then the new one replaces it (one active anchor per account, A-6), I can see the previous value before confirming, and all balances for that account reflect the new anchor.
- *Edge case, invalid input*: Given I enter a value that is not a number or an as-of date in the future, When I try to save, Then it is rejected with a clear message and nothing is saved.
- *Edge case, not a deposit account*: Given a credit-card or unknown-type account, When I look for an anchor option, Then none is offered, since those accounts never have balances.
- *Prompting*: Given a deposit account without an anchor, When I view the Dashboard balance section, Then that account is shown with an "anchor required" prompt that takes me to anchor entry.

### US-13.4: I can look up my balances for a date or month
**As** the Account Owner, **I want** to pick an exact date, or a month, and see each savings account's balance plus a combined total in SGD **so that** I know how much I had at any point in time.

**Traces to**: FR-AB-7, FR-AB-9, FR-AB-10, FR-AB-11, FR-AB-13, FR-AB-14, NFR-AB-1, NFR-AB-5, NFR-AB-7, A-5, A-8

**Acceptance Criteria**:
- *Happy path, exact date*: Given my accounts have anchors, When I choose a calendar date, Then I see each deposit account's end-of-day balance for that date in SGD, plus an all-accounts-combined total, on the Dashboard.
- *Happy path, month shortcut*: Given I choose a past month, When the lookup runs, Then it uses the last day of that month. Given I choose the current, still-in-progress month, Then it uses today (A-5).
- *Anchor date*: Given an account's anchor is dated T, When I look up T, Then the balance equals the anchor value (converted to SGD where needed).
- *After the anchor*: Given a date after T, When I look it up, Then the balance is the anchor plus the net of that account's inflows minus outflows after T up to and including the date.
- *Before the anchor*: Given a date before T, When I look it up, Then the balance is the anchor minus the net of that account's inflows minus outflows after the date up to and including T.
- *Foreign-currency account*: Given an account in a non-SGD currency, When I look up a date, Then its balance is worked out in its own currency and converted to SGD at the FX rate for the requested date, not the rates of the individual transactions.
- *Edge case, no FX rate available*: Given no usable FX rate exists for the requested date, When I look it up, Then that account's balance is shown as unavailable and left out of the combined total, and the total states that it excluded it.
- *Edge case, no anchor*: Given a deposit account with no anchor, When I look up a date, Then it shows "anchor required" and is left out of the combined total, and the total states the exclusion, even if that account's statements have printed closing balances (A-8).
- *Edge case, date after the latest ingested transaction*: Given I look up a date later than my most recent ingested transaction, When the result is shown, Then the view states the date through which transactions have been ingested, so the figure isn't mistaken for a live bank balance. The ingested-through date is shown on every lookup.
- *Exactness and speed*: Given the current data volume, When I run a lookup, Then results are exact to the cent and return without noticeable delay (NFR-AB-1, NFR-AB-5).
- *Edge case, no deposit accounts*: Given no deposit accounts exist yet, When I open the balance section, Then I see an explanatory empty state rather than a blank or error panel.
- *Presentation*: Given light or dark mode on a phone or a desktop, When I use the lookup, Then it is legible and usable in each (NFR-AB-7).

### US-13.5: I can see how my balance changed over time
**As** the Account Owner, **I want** a chart of my balance across a date range **so that** I can see the trend, not just one day's figure.

**Traces to**: FR-AB-12, FR-AB-13, NFR-AB-1, NFR-AB-7

**Acceptance Criteria**:
- *Happy path*: Given deposit accounts with anchors, When I pick a date range, Then the Dashboard shows a chart of the combined balance and each account's balance across that range.
- *Consistency with the lookup*: Given any plotted point, When I look up that same date in US-13.4, Then the figures match exactly.
- *Range spanning the anchor*: Given a range that begins before an account's anchor date, When the chart renders, Then the earlier points are computed backward from the anchor, the same as in US-13.4.
- *Edge case, excluded accounts*: Given an account with no anchor, When the chart renders, Then it is not plotted and the chart says which accounts are missing and why.
- *Edge case, missing FX rate*: Given a foreign-currency account has no usable FX rate for some date in the range, When the chart renders, Then that date is shown as a gap for that account rather than a guessed value.
- *Presentation*: Given light or dark mode on a phone or a desktop, When I view the chart, Then axes, labels, legend, and tooltips are legible in each, matching the Dashboard's existing chart theming (NFR-AB-7).
- *Granularity*: Whether the chart plots daily or month-end points is a Functional Design decision; whichever is chosen, every plotted point must satisfy the consistency criterion above.

### US-13.6: I'm warned when a statement's closing balance disagrees with my computed balance
**As** the Account Owner, **I want** each statement's printed closing balance checked against what the app computed from my anchor **so that** a wrong anchor or a missing transaction is flagged instead of silently producing a wrong balance.

**Traces to**: FR-AB-5, FR-AB-8, A-4

**Acceptance Criteria**:
- *Capture* (amended 2026-10-03, Scope Change): Given a statement that prints a closing balance for an account it holds, When it is ingested, Then that balance and the date it applies to are stored against that account within that statement, and the transaction list is unchanged, since the balance is never stored as a transaction. A statement holding several accounts stores one closing balance per account.
- *Happy path, agreement*: Given the balance computed from my anchor for a statement's closing date equals the printed closing balance, When the check runs, Then no warning is shown.
- *Happy path, mismatch*: Given the two differ, When the check runs, Then a visible discrepancy warning appears on the Dashboard naming the account and the statement and showing the size of the difference. Balances and the lookup keep working unchanged: the warning never blocks anything or silently alters a figure.
- *Edge case, no closing balance printed*: Given a statement that prints no closing balance, When it is ingested, Then it ingests normally and that statement simply has no cross-check.
- *Edge case, no anchor*: Given an account with no anchor, When the checks run, Then no cross-check is attempted and no spurious warning is raised for that account.
- *Resolution*: Given a discrepancy caused by a wrong anchor, When I correct the anchor so the figures agree, Then the warning disappears without any further action.
- *Tolerance*: Given a difference of a fraction of a cent or a rounding allowance, Then whether it counts as a mismatch follows the tolerance decided at Functional Design (A-4).

### US-13.7: I can safely re-ingest my existing statements so history gains accounts and balances
**As** the Account Owner, **I want** to re-ingest every statement I've already loaded, without losing the category corrections I made by hand, **so that** my history gains accounts, account types, and closing balances.

**Traces to**: FR-AB-15, FR-AB-16, FR-AB-17, NFR-AB-2

**Acceptance Criteria**:
- *Happy path, dry run*: Given I start the backfill, When it does its dry run, Then I see how many statements, transactions, manual category corrections, and dependent rows (recategorization jobs and proposals, categorization disagreements, recurring-payment matches) would be affected, and nothing has been changed.
- *Backup gate*: Given no verified backup of the affected data exists, When I try to proceed past the dry run, Then the backfill refuses to wipe anything. Given a backup exists, Then its location is reported to me.
- *Explicit confirmation*: Given the dry run and backup are done, When I have not explicitly confirmed, Then nothing is wiped. The backfill is never triggered by a deploy, a migration, or a normal ingestion run.
- *Happy path, reingest*: Given I confirm, When the backfill completes, Then every previously loaded PDF has gone through the normal ingestion pipeline again and every statement has an account, an account type, and (where printed) a closing balance.
- *Corrections preserved*: Given I had manually corrected categories before the backfill, When it completes, Then each correction is re-applied by matching on the statement's content hash, the transaction date, the amount, and the description.
- *Edge case, unmatched corrections*: Given a manual correction cannot be matched to a reingested transaction, When the backfill completes, Then it is listed individually in the report. None is dropped silently.
- *Edge case, files that fail to reingest*: Given some PDFs fail extraction during the reingest, When the backfill completes, Then those files are listed in the report with the reason, using the existing per-file ingestion outcomes, and are not silently skipped.
- *Completion report*: Given the backfill completes, When I read the report, Then it states how many recurring-payment matches were re-derived by ingestion-time matching, and which kinds of dependent rows were discarded.
- *Which PDFs hold several accounts* (added 2026-10-03, Scope Change): Given the backfill completes, When I read the report, Then it lists, for each statement, how many account sections it contained, and calls out every statement with more than one, so I learn from real results which of my PDFs are multi-account.
- *Edge case, a PDF that is no longer in Drive* (added 2026-10-03, Ingestion Worker Functional Design): Given an existing statement whose source PDF is missing from my Drive folder, When the backfill runs, Then that statement and everything depending on it is left exactly as it is, never wiped, and is listed in the report, since it could never be re-created.
- *Non-manual categories* (added 2026-10-03, Ingestion Worker Functional Design, Question 3 = A): Given transactions whose category was assigned by the pipeline and not by a manual correction of mine, When the backfill completes, Then they carry the pipeline's fresh categorization, which may differ from before. Only manual corrections are guaranteed to be preserved. Everything not dependent on transactions (categories, recurring-payment definitions, users, settings, OAuth credentials, FX rate cache) is unchanged.

---

## Traceability Summary

| Story | Requirements Covered |
|---|---|
| US-13.1 | FR-AB-1, FR-AB-2, FR-AB-4, NFR-AB-3, NFR-AB-8, A-1, A-2, A-3 |
| US-13.2 | FR-AB-3, A-3, A-6 |
| US-13.3 | FR-AB-6, A-6, A-7 |
| US-13.4 | FR-AB-7, FR-AB-9, FR-AB-10, FR-AB-11, FR-AB-13, FR-AB-14, NFR-AB-1, NFR-AB-5, NFR-AB-7, A-5, A-8 |
| US-13.5 | FR-AB-12, FR-AB-13, NFR-AB-1, NFR-AB-7 |
| US-13.6 | FR-AB-5, FR-AB-8, A-4 |
| US-13.7 | FR-AB-15, FR-AB-16, FR-AB-17, NFR-AB-2 |

Every FR-AB-1 through FR-AB-17 and A-1 through A-8 appears in at least one story. NFR-AB-4 (property-based tests for the pure balance function, unit tests elsewhere) and NFR-AB-6 (authentication on every new endpoint) are cross-cutting implementation constraints reflected across the stories rather than a dedicated story of their own, the same treatment earlier epics gave their testing NFRs.

## INVEST Check

- **Independent / Negotiable / Valuable / Testable**: all seven stories. Each delivers value to the Account Owner on its own, though US-13.4 to US-13.6 depend on accounts and anchors existing (US-13.1 to US-13.3), and US-13.7 is how historical data gains accounts in the first place.
- **Small / Estimable**: US-13.1 to US-13.6 are each a single capability. **US-13.7 is the largest**: it spans a dry run, a backup gate, reingest, correction re-apply, and reporting, and its exact mechanism (script, endpoint, or CLI, and where the backup is written) is deferred to Functional Design (Open Item in `account-balance-requirements.md`). It is kept as one story because its parts only make sense together as one safe, user-visible operation, but it may be split into smaller work items at Code Generation planning if its estimate proves too large.
