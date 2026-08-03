# User Stories — Bank Transaction Insights App

**Persona**: All stories are written for **The Account Owner** (see `personas.md`) — this is a single-persona application (Question 1 = A).
**Granularity**: Coarse, epic-level capability stories (Question 2 = A).
**Acceptance Criteria**: Given/When/Then happy path plus explicit edge-case scenarios (Question 3 = B).
**Traceability**: Each story references the requirements.md FR/NFR IDs it satisfies.

---

## Epic 1: Drive Ingestion & Extraction

### US-1.1: Connect my Google Drive account
**As** the Account Owner, **I want** to authenticate the app to my personal Google account via OAuth **so that** it can read my bank statements folder without me sharing my password.

**Traces to**: FR-1.1, FR-1.2, NFR-4.1

**Acceptance Criteria**:
- *Happy path*: Given I have not yet connected Google Drive, When I click "Connect Google Drive" and complete the Google OAuth consent screen, Then the app stores a refresh token and shows my connection as "Connected".
- *Edge case — token expiry/revocation*: Given my previously-stored refresh token has been revoked or expired, When I trigger an ingestion run, Then the app detects the auth failure, shows a clear "reconnect Google Drive" prompt, and does not crash or silently fail.
- *Edge case — consent declined*: Given I decline the OAuth consent screen, When I return to the app, Then it shows "Not connected" with an option to retry, and no partial/invalid token is stored.

### US-1.2: Trigger and monitor an ingestion run
**As** the Account Owner, **I want** to manually trigger a scan of my Drive folder and watch its progress **so that** I control exactly when new statements are pulled in.

**Traces to**: FR-1.3, FR-1.4, FR-1.5, NFR-2.2

**Acceptance Criteria**:
- *Happy path*: Given I am logged in and connected to Drive, When I click "Run Ingestion", Then the app lists PDF files in the configured folder, processes each one, and shows a live/near-live summary of files found, processed, skipped-as-duplicate, and failed.
- *Edge case — empty folder*: Given the Drive folder has no PDF files, When I trigger ingestion, Then the run completes immediately showing "0 files found" rather than erroring.
- *Edge case — partial failure*: Given 1 of 5 statements fails to parse, When the run completes, Then the other 4 statements' transactions are still committed, and the 1 failure is listed with a reason (per NFR-2.2 — no crash, no rollback of successful files).
- *Edge case — no auto-trigger*: Given I never click "Run Ingestion", When I use any other part of the app (login, browse dashboard, refresh page), Then no Drive scan occurs automatically (per FR-1.4).

### US-1.3: Extract transactions from a bank statement
**As** the Account Owner, **I want** the app to read each PDF (regardless of which bank or exact layout it uses) and pull out every transaction **so that** I don't have to type them in manually.

**Traces to**: FR-2.1, FR-2.2, FR-2.3, FR-2.4

**Acceptance Criteria**:
- *Happy path*: Given a text-based PDF bank statement, When it is processed during an ingestion run, Then the app extracts, for each transaction line, the date, description, out-flow or in-flow amount, and identifies the source bank name and currency from the statement content.
- *Edge case — scanned/image PDF*: Given a statement is a scanned image with no selectable text, When it is processed, Then the app runs OCR to extract the text before parsing transactions (per FR-2.1).
- *Edge case — unfamiliar layout*: Given a statement from a bank/layout never seen before, When it is processed, Then the layout-adaptive extraction still identifies transaction rows without requiring a code change (per FR-2.2).
- *Edge case — low-confidence extraction*: Given the extraction step cannot confidently identify transaction rows (e.g., corrupted PDF, unrecognizable layout), When processing that file, Then the statement is flagged as "needs review" / failed rather than silently producing wrong or partial transactions (per FR-2.5).

### US-1.4: Avoid duplicate processing of the same statement
**As** the Account Owner, **I want** statements I've already imported to be automatically skipped on future runs **so that** I never get duplicate transactions.

**Traces to**: FR-3.1, FR-3.2, FR-3.3

**Acceptance Criteria**:
- *Happy path*: Given a statement PDF was successfully processed in a prior run, When I run ingestion again with that same file still in the Drive folder, Then it is skipped and reported as "skipped (already processed)", with zero new transactions inserted for it.
- *Edge case — renamed but identical file*: Given the same PDF content is re-uploaded to Drive under a different filename, When ingestion runs, Then it is still recognized as a duplicate via the PDF file-content hash (per FR-3.1/FR-3.2) and skipped.
- *Edge case — genuinely modified statement*: Given a statement PDF's content actually changes (e.g., corrected/reissued statement with a different hash), When ingestion runs, Then it is treated as a new file and processed (not silently skipped).

### US-1.5: Review ingestion history
**As** the Account Owner, **I want** to see a history of past ingestion runs and their outcomes **so that** I can confirm nothing was missed or silently failed.

**Traces to**: FR-1.5, FR-3.3

**Acceptance Criteria**:
- *Happy path*: Given I have run ingestion at least once, When I open the ingestion history view, Then I see each run's timestamp, files found/processed/skipped/failed counts, and can drill into a run to see the per-file outcome.
- *Edge case — failed statement details*: Given a run had 1+ failed files, When I drill into that run, Then I see which file failed and why (e.g., "OCR unreadable", "layout not recognized"), so I know to investigate manually.

---

## Epic 2: Categorization & Learning

### US-2.1: Auto-categorize using similar past transactions
**As** the Account Owner, **I want** new transactions to inherit the category of very similar past transactions **so that** recurring merchants/payees get consistent categories without me re-tagging them every time.

**Traces to**: FR-5.1, FR-5.2 (steps 1–2), FR-5.3

**Acceptance Criteria**:
- *Happy path*: Given a past transaction with description "NTUC FAIRPRICE" was manually categorized as "Groceries", When a new transaction with a highly similar description ("NTUC FAIRPRICE #123") is extracted, Then it is auto-assigned "Groceries" as its category.
- *Edge case — manual correction outranks auto-assignment*: Given two past transactions with similar descriptions — one auto-assigned "Others" (never corrected) and one manually corrected to "Household" — When a new similar transaction is categorized, Then the manually-corrected precedent ("Household") is used, not the uncorrected auto-assignment (per FR-5.3).
- *Edge case — no similar transaction exists*: Given no past transaction is similar enough to the new one, When categorization runs, Then the system falls through to LLM-based classification (US-2.2) rather than forcing a weak match.

### US-2.2: Auto-categorize via LLM when no precedent exists
**As** the Account Owner, **I want** brand-new types of transactions to still get a sensible category guess **so that** I only have to manually categorize truly novel transactions.

**Traces to**: FR-5.1, FR-5.2 (step 3)

**Acceptance Criteria**:
- *Happy path*: Given a transaction description with no similar historical precedent, When categorization runs, Then an LLM call is made constrained to the whitelist categories, and the returned category (if valid) is assigned.
- *Edge case — LLM returns a category outside the whitelist*: Given the LLM's response is not one of the 46 whitelisted values, When the app processes the response, Then the transaction is assigned `UNSURE` rather than an invalid/free-text category.
- *Edge case — LLM call fails (timeout/error)*: Given the LLM API call errors out, When categorization runs, Then the transaction is still saved (not dropped) with category `UNSURE`, and the ingestion run summary is not blocked by this failure.

### US-2.3: See low-confidence categorizations flagged as UNSURE
**As** the Account Owner, **I want** transactions the system isn't confident about to be clearly marked `UNSURE` **so that** I know exactly which ones need my attention.

**Traces to**: FR-5.2 (step 4), FR-6.4

**Acceptance Criteria**:
- *Happy path*: Given neither similarity matching nor the LLM can confidently determine a category, When the transaction is saved, Then its category is set to the literal value `UNSURE` (uppercase).
- *Edge case — UNSURE visibility*: Given one or more transactions are `UNSURE`, When I view the transaction table, Then they are visually distinguishable (e.g., highlighted) and I can filter to show only `UNSURE` transactions (per FR-6.4).

---

## Epic 3: Transaction Review & Correction

### US-3.1: Browse all raw transactions
**As** the Account Owner, **I want** a table of every extracted transaction **so that** I have full visibility into my raw data.

**Traces to**: FR-6.1, FR-4.1, FR-4.2

**Acceptance Criteria**:
- *Happy path*: Given transactions exist in the database, When I open the transaction table, Then I see date, description, out-flow, in-flow, bank name, category, and currency for each, with a link/reference back to the source statement.
- *Edge case — no transactions yet*: Given no ingestion run has ever completed, When I open the transaction table, Then I see an empty state prompting me to run ingestion, not an error.

### US-3.2: Filter transactions
**As** the Account Owner, **I want** to filter the transaction table **so that** I can zero in on the data I care about.

**Traces to**: FR-7.1

**Acceptance Criteria**:
- *Happy path*: Given transactions from multiple banks, categories, and date ranges exist, When I apply a filter (date range, bank, category, in-flow/out-flow, currency, or free-text description search), Then only matching transactions are shown, and filters can be combined.
- *Edge case — filter yields zero results*: Given my filter combination matches nothing, When applied, Then I see a clear "no matching transactions" state rather than a blank/broken table.

### US-3.3: Group transactions
**As** the Account Owner, **I want** to group the transaction table **so that** I can see subtotals and patterns at a glance.

**Traces to**: FR-7.2, FR-7.3

**Acceptance Criteria**:
- *Happy path*: Given a set of (optionally filtered) transactions, When I group by category, bank, month/year, or category-source (auto/manual/UNSURE), Then the table shows grouped sections with per-group subtotals, and I can still sort within/across groups by date, amount, category, or bank.
- *Edge case — grouping with active filters*: Given I have both a filter and a grouping applied, When either changes, Then the grouped subtotals recompute to reflect only the filtered set (no stale totals).

### US-3.4: Manually correct a transaction's category
**As** the Account Owner, **I want** to fix a wrong or `UNSURE` category myself **so that** my data is accurate and future similar transactions benefit from my correction.

**Traces to**: FR-6.2, FR-6.3, FR-5.3, FR-5.4

**Acceptance Criteria**:
- *Happy path*: Given a transaction has an incorrect or `UNSURE` category, When I select a new category from the whitelist and save, Then the transaction is updated, flagged as manually-corrected (`category_source = manual`), and immediately reflected in the table/dashboards.
- *Edge case — attempting a non-whitelisted category*: Given I try to set a category not in the whitelist, When I attempt to save, Then the app rejects the input and only allows whitelist values (or `UNSURE`).
- *Edge case — correction affects future categorization*: Given I manually correct a transaction, When a new, similar-description transaction is later extracted, Then it is auto-categorized using my correction as precedent (per FR-5.3 / US-2.1 edge case).
- *Edge case — correction affects other existing UNSURE categorization*: Given I manually correct a transaction, When the correction is saved, Then existing `UNSURE` transactions are re-evaluated for similarity and any sufficiently similar ones are auto-categorized using my correction as precedent (per FR-5.4), rather than waiting for a future ingestion run to apply it.

### US-3.5: Quickly find and clear UNSURE transactions
**As** the Account Owner, **I want** a fast way to see and work through all `UNSURE` transactions **so that** my data doesn't accumulate uncategorized clutter.

**Traces to**: FR-6.4

**Acceptance Criteria**:
- *Happy path*: Given some transactions are `UNSURE`, When I apply the "UNSURE only" filter, Then I see just those transactions, in one place, ready for me to correct one by one (US-3.4).
- *Edge case — zero UNSURE transactions*: Given no transactions are currently `UNSURE`, When I apply the filter, Then I see a positive empty state (e.g., "Nothing needs review") rather than an error.

### US-3.6: Export the current view to CSV
**As** the Account Owner, **I want** to export my filtered/grouped transactions **so that** I can analyze them further offline or archive them.

**Traces to**: FR-7.4

**Acceptance Criteria**:
- *Happy path*: Given a filtered and/or grouped transaction view, When I click "Export CSV", Then a CSV file downloads containing exactly the currently visible/filtered transactions with all displayed columns.
- *Edge case — export with no results*: Given the current filter matches zero transactions, When I click "Export CSV", Then either the export is disabled or it downloads a header-only CSV — never an error.

### US-3.7: See original and converted amounts together
**As** the Account Owner, **I want** to see both the original currency amount and its SGD-converted equivalent **so that** I can trust the numbers without losing the original context.

**Traces to**: FR-10.2, FR-10.6, FR-2.4

**Acceptance Criteria**:
- *Happy path*: Given a transaction originally in USD, When I view it in the transaction table, Then I see both the original amount+currency (e.g., "$50.00 USD") and the converted SGD amount side by side.
- *Edge case — approximate conversion*: Given a transaction's converted amount used a fallback (nearest prior date) exchange rate (per FR-10.5), When displayed, Then it is visually marked as approximate (e.g., a "~" or tooltip) so I know it's not the exact-date rate.
- *Edge case — no rate available at all*: Given no exchange rate could be found for a transaction's currency, When displayed, Then the original amount/currency still shows normally, and the converted-amount field clearly indicates "not converted" rather than showing a blank or zero.

---

## Epic 4: Dashboards & Insights

### US-4.1: View spending-by-category trends
**As** the Account Owner, **I want** a dashboard of spending by category over time **so that** I can spot trends like rising grocery or dining spend.

**Traces to**: FR-8.1, FR-8.6

**Acceptance Criteria**:
- *Happy path*: Given categorized transactions spanning multiple months, When I open the category-trends dashboard, Then I see a chart of spend per category per month, computed in SGD (per FR-8.6).
- *Edge case — sparse data*: Given only one month of data exists, When I open the dashboard, Then it renders a single-period view rather than an empty/broken chart.

### US-4.2: View income vs. expenses / net cash flow
**As** the Account Owner, **I want** a cash-flow dashboard **so that** I can see whether I'm net positive or negative each month.

**Traces to**: FR-8.2, FR-8.6

**Acceptance Criteria**:
- *Happy path*: Given transactions with both in-flows and out-flows exist, When I open the cash-flow dashboard, Then I see total income, total expenses, and net cash flow per month (in SGD), across the selected date range.
- *Edge case — a month with only expenses or only income*: Given a month has zero in-flows (or zero out-flows), When displayed, Then that side of the chart correctly shows zero rather than being omitted or erroring.

### US-4.3: View bank-level breakdowns
**As** the Account Owner, **I want** to see totals and trends broken down per bank **so that** I understand how my finances are distributed across accounts.

**Traces to**: FR-8.3, FR-8.6

**Acceptance Criteria**:
- *Happy path*: Given transactions from multiple banks, When I open the bank-breakdown dashboard, Then I see per-bank totals (in SGD) and trend over time, for the selected date range.
- *Edge case — single bank only*: Given only one bank's statements have been ingested so far, When viewed, Then the dashboard still renders correctly for that one bank (no assumption of multiple banks).

### US-4.4: Filter dashboards by date range and currency
**As** the Account Owner, **I want** to adjust the date range and currency scope on any dashboard **so that** I can focus on the period/accounts I care about.

**Traces to**: FR-8.4

**Acceptance Criteria**:
- *Happy path*: Given I'm viewing any dashboard, When I change the date range or currency filter, Then all charts on that dashboard update to reflect the new scope, with clear currency labeling on all monetary figures.
- *Edge case — date range with no data*: Given I select a date range with no transactions, When applied, Then dashboards show an explicit "no data for this period" state rather than blank/broken charts.

### US-4.5: Drill down from a chart to underlying transactions
**As** the Account Owner, **I want** to click into a chart segment **so that** I can see exactly which transactions make up a number I'm curious about.

**Traces to**: FR-8.5

**Acceptance Criteria**:
- *Happy path*: Given I'm viewing the category-trends dashboard, When I click a specific category/month segment, Then I'm taken to the transaction table pre-filtered to that category and month.
- *Edge case — drill-down on a zero-value segment*: Given I click a segment representing zero transactions (e.g., an empty gap in the trend line), When drilled into, Then the transaction table shows correctly as empty for that filter, not an error.

### US-4.6: See when a dashboard figure includes approximated conversions
**As** the Account Owner, **I want** to know if a dashboard total includes approximated or missing currency conversions **so that** I don't over-trust a number that's partially estimated.

**Traces to**: FR-10.5, FR-8.6

**Acceptance Criteria**:
- *Happy path*: Given all transactions in a dashboard's scope had exact-date FX rates available, When viewed, Then no approximation indicator is shown.
- *Edge case — some transactions used fallback rates*: Given one or more transactions in scope used a fallback (nearest prior date) rate, When the dashboard total is displayed, Then an indicator/tooltip discloses that the total includes approximated conversions.
- *Edge case — some transactions excluded (no rate at all)*: Given one or more transactions in scope had no FX rate available and were excluded from the aggregate (per FR-10.5), When the dashboard total is displayed, Then an indicator discloses that N transactions were excluded from this total, with a link to see them in the raw transaction view.

---

## Epic 5: Access & Configuration

### US-5.1: Log in to the app
**As** the Account Owner, **I want** a simple login **so that** only I can view my financial data.

**Traces to**: FR-9.1, FR-9.2

**Acceptance Criteria**:
- *Happy path*: Given valid configured credentials, When I enter my username and password on the login screen, Then I gain access to the app and stay logged in for a reasonable session duration.
- *Edge case — wrong credentials*: Given I enter an incorrect password, When I submit, Then I see a generic "invalid credentials" error (no hint about which field was wrong) and remain logged out.
- *Edge case — unauthenticated access attempt*: Given I am not logged in, When I try to directly access any app page or API route, Then I am redirected/denied and prompted to log in (per FR-9.1 — no page or API is accessible without auth).

### US-5.2: Edit the category whitelist
**As** the Account Owner, **I want** to add, rename, or remove categories from the whitelist **so that** the list stays relevant as my life/finances change without needing a code change.

**Traces to**: FR-4.3, Requirements Section 5

**Acceptance Criteria**:
- *Happy path*: Given I open category settings, When I add a new category, Then it becomes immediately selectable for manual corrections (US-3.4) and future auto-categorization.
- *Edge case — removing a category still in use*: Given I try to remove a category that existing transactions currently use, When I attempt the removal, Then the app warns me and either blocks the removal or requires me to reassign those transactions first (no orphaned/invalid category references).
- *Edge case — renaming a category*: Given I rename an existing category, When saved, Then all existing transactions using it are updated to the new name (no silent mismatch between historical and current data).

### US-5.3: Configure external service credentials
**As** the Account Owner, **I want** to set up my Google OAuth client, LLM API key, and FX-rate API access via environment configuration **so that** the app can reach the external services it depends on, without secrets living in source control.

**Traces to**: NFR-4.1, NFR-1.2

**Acceptance Criteria**:
- *Happy path*: Given I populate the `.env` file with the required secrets before first `docker-compose up`, When the app starts, Then it successfully connects to Google Drive, the LLM provider, and the FX-rate API using those values.
- *Edge case — missing required secret*: Given a required secret (e.g., LLM API key) is missing at startup, When the app starts, Then it fails fast with a clear error naming the missing configuration, rather than starting in a broken/partial state.

---

## Traceability Summary

| Epic | Stories | Requirements Covered |
|---|---|---|
| 1. Drive Ingestion & Extraction | US-1.1 – US-1.5 | FR-1.1–1.5, FR-2.1–2.5, FR-3.1–3.3, NFR-2.2, NFR-4.1 |
| 2. Categorization & Learning | US-2.1 – US-2.3 | FR-5.1–5.3 |
| 3. Transaction Review & Correction | US-3.1 – US-3.7 | FR-4.1–4.3, FR-5.4, FR-6.1–6.4, FR-7.1–7.4, FR-10.2, FR-10.6 |
| 4. Dashboards & Insights | US-4.1 – US-4.6 | FR-8.1–8.6, FR-10.5 |
| 5. Access & Configuration | US-5.1 – US-5.3 | FR-9.1–9.2, NFR-1.2, NFR-4.1, Category Whitelist (Requirements Section 5) |

All FR/NFR items in `requirements.md` are represented by at least one story above (Step G traceability check — complete, no gaps found).
