# Requirements Change — Clarification Questions

Your requested change to add **automated currency conversion to a single reporting currency** needs two design decisions before I update the requirements. Please answer below.

## Question 1 — Reporting Currency
Which currency should all converted totals be reported in (used for dashboards and any converted views)?

A) SGD (Singapore Dollar)

B) USD (US Dollar)

C) Another currency — specify after [Answer]: tag below

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 2 — Exchange Rate Source & Timing
How should exchange rates be obtained, and which rate should apply to a given transaction?

A) Use a free/public exchange-rate API (e.g., exchangerate.host, ECB feed) fetched at ingestion time, applying the rate for the transaction's own date (historical rate lookup per transaction)

B) Use a free/public exchange-rate API, but apply only the latest available rate to all transactions (simpler, less historically accurate)

C) Use a manually-maintained exchange rate table that the user enters/updates in the UI (no external API dependency)

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 3 — Original Amount Preservation
Should the original (pre-conversion) amount and currency still be visible/retained alongside the converted amount, or should conversion replace the stored value?

A) Retain both — store original amount+currency as the source of truth, compute converted amount for display/aggregation on top (recommended; avoids lossy re-conversion)

B) Convert and store only the reporting-currency amount (original amount/currency discarded after conversion)

X) Other (please describe after [Answer]: tag below)

[Answer]:A
