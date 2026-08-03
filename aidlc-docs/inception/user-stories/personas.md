# Personas — Bank Transaction Insights App

Per plan decision (Question 1 = A), this is modeled as a single persona covering both first-time setup and ongoing use.

## Persona: The Account Owner

- **Who they are**: The single end user of the application — owns the Google Drive folder containing their bank statements, owns the app's login credentials, and is the sole consumer of its dashboards and transaction data.
- **Goals**:
  - Get an accurate, up-to-date picture of spending and cash flow across multiple banks and currencies without manually transcribing statements
  - Trust that categorization is "mostly right" out of the box and easy to correct when it isn't
  - Avoid duplicate or messy data from re-running ingestion
  - Spend minutes, not hours, reviewing new transactions after each ingestion run
- **Technical comfort**: Comfortable running `docker-compose up` and doing a one-time OAuth consent flow; not a developer — expects a polished, self-explanatory UI for everything after setup.
- **Frequency of use**: Periodic/manual — logs in, triggers an ingestion run when new statements have landed in Drive, reviews/corrects a handful of transactions, checks dashboards. Not a daily-active-user pattern.
- **Pain points this app addresses**: Manually reading PDFs and copying transactions into a spreadsheet; inconsistent categorization; losing track of which statements were already processed; no single view across multiple banks/currencies.
- **Relevant requirements this persona drives**: All functional requirements (FR-1 through FR-10) are experienced directly by this persona; there is no secondary/admin/service persona in this system per NFR-9 (single-user, no multi-user account management).
