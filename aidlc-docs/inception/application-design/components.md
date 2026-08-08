# Components — Bank Transaction Insights App

Architectural style: **Separate services** (Question 1 = B) — an **API Service** and an **Ingestion Worker Service**, both sharing one PostgreSQL-class database, plus a **Frontend** SPA. Components below are grouped by which deployable service owns them.

---

## Frontend

### Frontend SPA
- **Purpose**: Rich single-page web application — the only surface the Account Owner interacts with directly.
- **Responsibilities**: Login screen; ingestion trigger + live progress/run history views; transaction table with filter/group/sort/export; manual category correction UI; dashboards (category trends, cash flow, bank breakdowns) with drill-down; category whitelist settings.
- **Interfaces**: Consumes the API Service's REST API (Question 4 = A) exclusively — never talks to the Ingestion Worker or database directly.
- **Stories covered**: All 24 (as the presentation layer for every capability).
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: Adds a Review page (US-6.4) and a pending-proposal-count nav badge (US-6.6), consuming the new Recategorization Review Component's endpoints. Follows this component's existing convention of one Frontend SPA component covering every page, not a component per page.
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds a "Backup Status" panel to the Review page (US-7.4), visually separate from the existing ProposalTable, consuming the new Backup Status Component's endpoint. Same convention — one Frontend SPA component, no new component for the panel.

---

## API Service Components

### Auth Component
- **Purpose**: Protect the entire application behind a single-user login.
- **Responsibilities**: Validate credentials, issue/validate session (e.g., session cookie or JWT), reject unauthenticated requests to any other API Service route.
- **Stories covered**: US-5.1

### Transaction Management Component
- **Purpose**: Owns all read/write access to transaction data on behalf of the user-facing UI.
- **Responsibilities**: List/filter/group/sort transactions; return a single transaction's detail (original + converted amount); apply manual category corrections and mark `category_source = manual`; trigger the retroactive-UNSURE-recategorization job (FR-5.4) after a correction; CSV export of the current filtered/grouped view.
- **Stories covered**: US-3.1, US-3.2, US-3.3, US-3.4, US-3.5, US-3.6, US-3.7

### Dashboard/Insights Component
- **Purpose**: Serve aggregate, SGD-converted financial insight queries to the Frontend.
- **Responsibilities**: Category-trend aggregation; income-vs-expense/cash-flow aggregation; bank-level breakdown aggregation; apply date-range/currency filters; surface approximate-conversion / excluded-transaction disclosures per transaction set.
- **Stories covered**: US-4.1, US-4.2, US-4.3, US-4.4, US-4.5, US-4.6

### Ingestion Trigger & Status Component
- **Purpose**: The API Service's side of the async ingestion workflow — never performs extraction/categorization itself.
- **Responsibilities**: Accept a "start ingestion run" request from the Frontend and enqueue a run record for the Ingestion Worker; expose run status/progress (for polling) and run history for past runs, including per-file outcomes and failure reasons.
- **Stories covered**: US-1.2, US-1.5
- **Addendum (2026-08-01, during Unit 3 NFR Requirements)**: also owns the Google Drive OAuth connect/callback handshake (US-1.1) — added retroactively since Unit 3 (Ingestion Worker) has no browser-facing interface of its own to run an interactive OAuth flow; see `construction/api-service/code/api-layer-summary.md` and `audit.md` for the full history.

### Recategorization Review Component
- **Addendum (2026-08-02, Recategorization Review Panel feature — see `recategorization-review-application-design-plan.md`)**
- **Purpose**: Owns the human-in-the-loop review of proposed category changes that the Categorization Engine (Ingestion Worker) generates but doesn't auto-apply.
- **Responsibilities**: List pending proposals with enough context to judge them (candidate transaction, proposed category, match score/bucket, triggering correction); approve or reject a proposal individually or in bulk, writing the category directly to the transaction on approval; expose a pending count for the nav badge.
- **Interfaces**: New REST endpoints, consumed by the Frontend SPA's new Review page. Depends only on the Shared Data Store (reads/writes proposal rows and, on approval, the `transactions` table) — never calls the Ingestion Worker Service directly, matching this project's one hard architectural rule.
- **Stories covered**: US-6.4, US-6.5, US-6.6

### Backup Status Component
- **Addendum (2026-08-08, Nightly Transaction Backup feature — see `nightly-backup-application-design-plan.md`)**
- **Purpose**: Exposes the Ingestion Worker Service's nightly backup history/status to the Frontend, read-only.
- **Responsibilities**: Report the outcome of the most recent backup attempt (success, or failure with a failure category — `drive_connectivity` vs `other`) so the Review page's Backup Status panel can render the right message.
- **Interfaces**: New REST endpoint(s), consumed by the Frontend SPA's Backup Status panel. Depends only on the Shared Data Store (reads the new `backup_runs` table) — never calls the Ingestion Worker Service directly, matching this project's one hard architectural rule (same as the Recategorization Review Component).
- **Stories covered**: US-7.4

### Configuration Component
- **Purpose**: Manage user-editable configuration that isn't a secret.
- **Responsibilities**: List/add/rename/remove categories in the whitelist; validate that a category removal doesn't orphan existing transactions (block or require reassignment first).
- **Stories covered**: US-5.2

**Note**: Secrets configuration (US-5.3 — Google OAuth client, LLM API key, FX API key) is environment-variable-based at container startup (NFR-4.1), not a runtime API Service responsibility; both services read their own required secrets from their own environment at boot and fail fast if missing.

---

## Ingestion Worker Service Components

### Drive Connector Component
- **Purpose**: All interaction with Google Drive.
- **Responsibilities**: Perform/refresh OAuth authentication; list PDF files in the configured folder; download file bytes for processing.
- **Stories covered**: US-1.1, part of US-1.2
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds write-side operations against the separate, dedicated backup Drive folder (distinct from the ingestion source folder): ensure the `backup` subfolder exists (creating it if needed), upload a file, list files in that subfolder, and delete a file. Reuses the same shared OAuth credential and the existing retry/transient-error pattern already used for list/download. Still "all interaction with Google Drive" — no new component needed.

### Backup Manager Component
- **Addendum (2026-08-08, Nightly Transaction Backup feature — see `nightly-backup-application-design-plan.md`)**
- **Purpose**: Owns the nightly transaction backup capability — a time-triggered concern, distinct from the queue-triggered Ingestion Orchestrator.
- **Responsibilities**: Detect when a backup is due (scheduled time reached, or a missed backup needs to catch up per FR-8); export a full snapshot of all transactions to CSV; upload it via the Drive Connector Component to the dedicated backup folder's `backup` subfolder; enforce retention (keep the 7 most recent, delete older, scoped only to this feature's own files); record the outcome (success, or failure with a failure category) for the Backup Status Component to read.
- **Stories covered**: US-7.1, US-7.2, US-7.3, US-7.4 (status-recording side)

### Duplicate Detection Component
- **Purpose**: Prevent reprocessing of already-imported statements.
- **Responsibilities**: Compute a hash of each downloaded PDF's raw bytes; check it against the processed-statements record; record the Drive file ID + hash once a statement is successfully processed.
- **Stories covered**: US-1.4

### Statement Extraction Component
- **Purpose**: Turn a PDF (bytes) into structured transaction rows.
- **Responsibilities**: OCR fallback for scanned/image PDFs; layout-adaptive, LLM-assisted parsing to identify transaction date/description/amounts, bank name, and currency; flag a statement as failed/needs-review when extraction confidence is too low.
- **Stories covered**: US-1.3

### Categorization Engine Component (pluggable — Question 3 = A)
- **Purpose**: Assign a whitelist category (or `UNSURE`) to a transaction.
- **Responsibilities**: Defines a `CategorizationStrategy` interface with two concrete strategies — **Similarity Matcher** (fuzzy-matches against past transactions, prioritizing manually-corrected precedent per FR-5.3) and **LLM Classifier** (fallback, constrained to the whitelist). Orchestrates the fallback chain (similarity → LLM → UNSURE) per FR-5.2. Also handles the retroactive re-scan of existing `UNSURE` transactions triggered by a manual correction (FR-5.4), invoked via an async job from the API Service.
- **Stories covered**: US-2.1, US-2.2, US-2.3, US-3.4 (retro edge case)
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: The retroactive re-scan (FR-5.4) is broadened and now split in two — searching `UNSURE` transactions *and* already-categorized transactions (US-6.1); auto-applying only very-high-confidence `UNSURE` matches as before (US-6.2), and always creating a pending proposal row (consumed by the new Recategorization Review Component) for everything else, including *every* match against an already-categorized transaction regardless of score (US-6.3). No new external dependency — reuses the existing similarity matcher.

### Currency Conversion Component
- **Purpose**: Compute a converted SGD amount for each transaction.
- **Responsibilities**: Fetch/cache historical FX rates per currency-pair/date from a public FX API; apply nearest-prior-date fallback when the exact date is unavailable and flag the result as approximate; leave a transaction unconverted (but still visible with its original amount) when no rate can be found at all.
- **Stories covered**: US-3.7, US-4.6

### Ingestion Orchestrator Component
- **Purpose**: The Worker Service's coordination layer — the only component that calls the others in sequence.
- **Responsibilities**: Pick up a queued run request; for each file: Drive Connector download → Duplicate Detection check → (if new) Statement Extraction → Categorization Engine → Currency Conversion → persist transactions; update run/file-level progress and status continuously so the API Service's polling reflects near-live state; ensure one file's failure doesn't abort the run (NFR-2.2).
- **Stories covered**: US-1.2, US-1.5 (progress/history data producer)

---

## Shared Data Store

### PostgreSQL-class Database (shared, not a "component" with behavior — see NFR Requirements for exact engine choice)
- Owns: users/credentials, transactions, processed-statements, category whitelist, ingestion runs (job/status/history), FX-rate cache.
- Both the API Service and the Ingestion Worker Service connect to it directly with their own data-access code — they are **not** coupled via a shared in-process library (they're separate deployables per Question 1 = B), only via the shared schema (a data contract, documented in `component-dependency.md`).
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: Adds a recategorization-proposal record, child of the existing `recategorization_jobs` row — written by the Ingestion Worker's Categorization Engine, read/updated by the API Service's new Recategorization Review Component. Exact table shape is a Functional Design (Database unit) decision.
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds a `backup_runs` tracking table — written by the Ingestion Worker's new Backup Manager Component, read by the API Service's new Backup Status Component. Exact table shape is a Functional Design (Database unit) decision.
