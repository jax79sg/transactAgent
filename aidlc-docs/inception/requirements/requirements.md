# Requirements — Bank Transaction Insights Application

## 1. Intent Analysis Summary

- **User Request**: A web application with a rich UI that ingests the user's bank statement PDFs from a private Google Drive folder (OAuth-gated), extracts transactions into a database, auto-categorizes them using a whitelist with learning from past manually-corrected transactions, prevents duplicate reprocessing, and provides a reviewable/filterable transaction table plus financial insight dashboards. Fully containerized via docker-compose.
- **Request Type**: New Project (greenfield)
- **Scope Estimate**: System-wide (multiple components: Drive/OAuth integration, PDF extraction pipeline, categorization engine, database, backend API, frontend UI, dashboards, containerization)
- **Complexity Estimate**: Complex — multiple external integrations (Google OAuth/Drive, PDF/OCR extraction, LLM-assisted categorization), variable/unknown document layouts, stateful learning behavior, multi-currency data model, and full containerized deployment

## 2. Functional Requirements

### FR-1: Google Drive Ingestion
- FR-1.1: The system SHALL authenticate to Google Drive using OAuth 2.0 Authorization Code flow against the user's personal Google account.
- FR-1.2: On first run, the system SHALL guide the user through an interactive OAuth consent flow and persist the resulting refresh token securely for subsequent runs.
- FR-1.3: The system SHALL only scan the configured Google Drive folder (`https://drive.google.com/drive/folders/1qeJblYSk-E6BH6dhenbc8Vd0xxRkZor0`) for PDF files.
- FR-1.4: The system SHALL only scan/process the Drive folder when explicitly triggered by the user via a UI action (button), never on a schedule or automatically on page load.
- FR-1.5: The system SHALL display progress and results of each ingestion run (files found, files processed, files skipped as duplicates, files failed, transactions extracted).

### FR-2: Statement Parsing & Transaction Extraction
- FR-2.1: The system SHALL extract text from each bank statement PDF, including OCR fallback for scanned/image-based PDFs (per user confirmation that some statements may be scanned).
- FR-2.2: The system SHALL support a generic, layout-adaptive extraction approach (not hard-coded per-bank templates) capable of handling both deposit/checking and credit-card statement formats, since the exact set and layout of banks is not fixed in advance. An LLM-assisted extraction step SHALL be used to identify and structure transaction rows, bank name, and account/currency information from arbitrary statement layouts.
- FR-2.3: For each transaction, the system SHALL extract: Transaction Date, Transaction Description, Out-flow amount (if applicable), In-flow amount (if applicable), and identify the source Bank name from the statement content.
- FR-2.4: The system SHALL identify and store the currency of each transaction (statements may be in different currencies across banks/accounts).
- FR-2.5: If extraction confidence is low or a statement cannot be parsed, the system SHALL flag the statement/file as "failed" or "needs review" rather than silently dropping it, and surface this in the ingestion run results (FR-1.5).

### FR-3: Duplicate Statement Prevention
- FR-3.1: The system SHALL compute a hash of each statement's raw PDF file (file bytes) and record it, along with the Google Drive file ID, once a statement has been successfully processed.
- FR-3.2: On each ingestion run, the system SHALL skip any file whose PDF-content hash already exists in the processed-statements record, preventing duplicate transaction insertion (this also catches a file that was renamed or re-uploaded to Drive but is byte-identical).
- FR-3.3: The processed-statement record SHALL be queryable/visible to the user (e.g., an ingestion history view).

### FR-4: Transaction Data Model & Storage
- FR-4.1: Each transaction SHALL be persisted with at minimum: Transaction Date, Transaction Description, Out-flow, In-flow, Bank name, Transaction Category, and Currency.
- FR-4.2: The system SHALL also retain a link back to the source statement/file for traceability (e.g., which Drive file and which ingestion run produced the transaction).
- FR-4.3: The database SHALL support all categories in the whitelist below (Section 5) plus the literal fallback value `UNSURE`.

### FR-5: Transaction Categorization
- FR-5.1: For each extracted transaction, the system SHALL assign exactly one category from the whitelist (Section 5) or `UNSURE`.
- FR-5.2: The system SHALL use a hybrid categorization strategy:
  1. Search for similar past transactions (by description text similarity) that have a confirmed category (auto-assigned-and-unedited or manually-corrected).
  2. If a sufficiently similar past transaction exists, assign its category as precedent.
  3. If no sufficiently similar past transaction exists, fall back to an LLM-based classification call, constrained to the whitelist, using the transaction description (and optionally nearby transactions/context) as input.
  4. If the LLM/similarity process cannot confidently determine a category, assign `UNSURE`.
- FR-5.3: Manually-corrected categories (see FR-6) SHALL be prioritized as the strongest precedent signal in the similarity search (FR-5.2 step 1), ranked above auto-assigned/unedited historical categorizations.
- FR-5.4: When a transaction's category is manually corrected, the system SHALL re-evaluate existing `UNSURE` transactions for similarity against the newly-corrected transaction, and auto-categorize any sufficiently similar `UNSURE` transactions using that correction as precedent.

### FR-6: Manual Review & Correction
- FR-6.1: Users SHALL be able to view all raw extracted transactions in a table/list view.
- FR-6.2: Users SHALL be able to manually change the category of any transaction.
- FR-6.3: Manual corrections SHALL be persisted and flagged (e.g., `category_source = manual`) so they can be prioritized as future categorization precedent (FR-5.3).
- FR-6.4: Users SHALL be able to identify at a glance which transactions are categorized as `UNSURE` (e.g., visual highlight or dedicated filter) to prioritize review.

### FR-7: Transaction Review, Grouping & Filtering
- FR-7.1: The system SHALL provide a transaction table view supporting filtering by: date range, bank name, category, in-flow vs out-flow, currency, and free-text description search.
- FR-7.2: The system SHALL support grouping transactions by: category, bank, month/year, and category-source (auto vs manual vs UNSURE).
- FR-7.3: The system SHALL support sorting the transaction table by date, amount, category, and bank.
- FR-7.4: The system SHALL support exporting the currently filtered/grouped transaction view (e.g., CSV export) for offline analysis.

### FR-8: Financial Insight Dashboards
- FR-8.1: The system SHALL provide a dashboard showing spending by category over time (trend lines / monthly breakdowns).
- FR-8.2: The system SHALL provide a dashboard showing income vs. expenses / net cash flow over time.
- FR-8.3: The system SHALL provide a dashboard showing bank/account-level breakdowns (totals and trends per bank).
- FR-8.4: Dashboards SHALL support filtering by date range and by currency, and SHALL clearly indicate currency context for all displayed monetary figures.
- FR-8.5: Dashboards SHALL be interactive (e.g., drill down from a category trend into the underlying transaction list).
- FR-8.6: All aggregate/summary figures on dashboards (category totals, cash flow, bank totals) SHALL be computed in the converted reporting currency (SGD) per FR-10, so multi-currency transactions can be summed together meaningfully.

### FR-10: Automated Currency Conversion
- FR-10.1: The system SHALL designate SGD (Singapore Dollar) as the single reporting currency for all converted/aggregate views.
- FR-10.2: The system SHALL retain each transaction's original amount and original currency as the source of truth (FR-4.1/FR-2.4 unchanged); conversion SHALL NOT overwrite or discard the original value.
- FR-10.3: The system SHALL compute a converted (reporting-currency) amount for each transaction using a historical exchange rate for that transaction's own date, sourced from a free/public exchange-rate API.
- FR-10.4: The system SHALL cache/persist fetched exchange rates (by currency pair and date) so repeated ingestion or dashboard recalculation does not require redundant API calls.
- FR-10.5: If an exchange rate cannot be obtained for a given currency/date (e.g., API unavailable, unsupported currency, or non-trading-day date), the system SHALL fall back to the nearest available prior date's rate and flag the transaction's converted amount as approximate; if no rate can be found at all, the transaction SHALL be excluded from converted aggregates but SHALL still appear in the raw transaction view with its original amount/currency.
- FR-10.6: The transaction table view (FR-7) SHALL be able to display both the original amount/currency and the converted SGD amount per transaction.

### FR-9: Web Application Access Control
- FR-9.1: The web application SHALL require a simple username/password login to access any page or API (single-user; no self-service registration or multi-user account management required).
- FR-9.2: Credentials SHALL be configured via environment variables / initial setup, not hardcoded.

## 3. Non-Functional Requirements

### NFR-1: Architecture & Deployment
- NFR-1.1: The entire application (frontend, backend, database, and any supporting services) SHALL be fully containerized and startable via a single `docker-compose up` command.
- NFR-1.2: The system is intended primarily for local/personal deployment today, but configuration (secrets, external URLs, OAuth credentials) SHALL be externalized via environment variables / `.env` file rather than hardcoded, to ease a future move to cloud hosting.
- NFR-1.3: Technology stack selection is delegated to the AI/architect; a modern, well-supported stack SHALL be chosen and documented during NFR Requirements (Construction phase).

### NFR-2: Data Integrity
- NFR-2.1: Transaction and processed-statement data SHALL persist across container restarts (durable volume-backed database).
- NFR-2.2: Ingestion SHALL be resilient to partial failure — a failure parsing one statement SHALL NOT abort processing of other statements in the same run, and SHALL NOT corrupt already-committed data.

### NFR-3: Usability
- NFR-3.1: The UI SHALL be a "rich" single-page application experience (responsive, interactive filtering/grouping without full page reloads, interactive charts).

### NFR-4: Secrets Handling
- NFR-4.1: Google OAuth client credentials and refresh tokens, LLM API keys, and web app login credentials SHALL be stored as environment-configured secrets, never committed to source control or exposed in client-side code.

### NFR-5: Extension Configuration (per user opt-in during clarification)
- NFR-5.1: **Security Baseline extension**: NOT enforced as blocking (user opted out — personal/PoC-style project). Sensible baseline secret handling (NFR-4) still applies as a core requirement, independent of the extension.
- NFR-5.2: **Property-Based Testing extension**: Enforced in **Partial** mode — PBT rules PBT-02, PBT-03, PBT-07, PBT-08, PBT-09 apply as blocking constraints wherever pure functions or serialization/parsing round-trips exist (e.g., statement text → structured transaction parsing, category-matching similarity functions). Other PBT rules are advisory only.
- NFR-5.3: **Resiliency Baseline extension**: NOT enforced (user opted out — personal-use project, rapid iteration prioritized over formal resiliency posture).

## 4. Key Technical Decisions Confirmed by User

| Topic | Decision |
|---|---|
| Google identity | Personal Google account, interactive OAuth Authorization Code flow, refresh token persisted |
| PDF format | Mixed — some scanned/image-based; OCR fallback required |
| Bank/layout coverage | Unknown/variable; generic, LLM-assisted extraction (no hard-coded per-bank parsers) |
| Categorization method | Hybrid: fuzzy similarity search against past transactions first, LLM fallback when no strong match |
| Manual correction learning | Manual edits ARE fed back as prioritized precedent for future auto-categorization |
| Duplicate detection | Hash of the raw PDF file bytes, alongside Drive file ID (updated per user request 2026-08-01 — supersedes earlier content-hash-of-text and hash-of-Drive-ID answers) |
| Web app auth | Single user, simple login/password protecting the UI |
| Currency | Multi-currency — store original currency per transaction; auto-convert to SGD (reporting currency) for aggregates using historical FX rates from a public API, original amount always retained (updated 2026-08-01) |
| Dashboards | Comprehensive: category trends, cash flow, per-bank breakdowns |
| Tech stack | AI/architect to choose best-fit modern stack |
| Deployment | Local via docker-compose now; externalized config for future cloud portability |

## 5. Category Whitelist

The following 45 categories are whitelisted (user-supplied, verbatim), plus the reserved fallback category `UNSURE` (46 total). This list is stored as configuration/seed data so the user can edit it later without a code change.

Baby, Bills, Car, Cash, Clothing, Course, Dining, Entertainment, Gift, Groceries, Household, Income, Insurance, Interest, Learning, Loans, Maid, Medical, Mother, Online Shopping, Pets, Tax, Transport, Bank charges, Hair, Ling Tuition, Gambling, Claims, Others, Amber Park, Preschool, Gray Lane, Petrol, Parking, Conservancy, Car Loan, Home Loan, Mogi, Ling allowance, Wife, Work, Fraud, RovingVets, Electronics, One Time

**Reserved fallback**: `UNSURE` (used whenever the system cannot confidently assign one of the above)

## 6. Out of Scope (for this phase)

- Automatic/scheduled ingestion (explicitly manual-trigger only per FR-1.4)
- Multi-user account management / registration flows
- Formal AWS Well-Architected resiliency review (extension opted out)
- Formal security compliance review (extension opted out; baseline secret hygiene still required per NFR-4)

## 7. Summary

This is a personal-use, single-user financial insights web application, fully containerized. It manually pulls bank statement PDFs from a private Google Drive folder via OAuth, extracts transactions using an OCR + LLM-assisted, layout-adaptive pipeline, categorizes each transaction using a similarity-first / LLM-fallback strategy against a 46-entry whitelist (with manual corrections prioritized as learning precedent), prevents duplicate re-processing via a hash of the raw PDF file, auto-converts multi-currency transactions to SGD for aggregate reporting (via historical public FX rates, original amounts always retained), and exposes a login-protected UI for reviewing/filtering/grouping transactions plus rich financial dashboards (category trends, cash flow, per-bank breakdowns).
