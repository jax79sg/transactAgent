# Application Design Plan — Account Balance at a Point in Time

**Role**: Software architect, identifying components/methods/services/dependencies for Epic 13.

Please answer the two questions at the bottom by filling in the letter after each `[Answer]:` tag. If none of the options fit, choose the last option (Other) and describe your preference. Let me know when you're done.

## Design decisions made and explained (not asked), with reasoning

Each is a technical call with a single defensible answer given this project's own established conventions, not a product-owner tradeoff:

| Category | Decision | Why this isn't a question |
|---|---|---|
| **Component identification (Ingestion Worker)** | Extend the existing **Statement Extraction Component** (schema + prompt gain an account identifier, account type, and closing balance with its date; all existing safety nets stay unchanged). Add one new small **Account Resolver Component** that the existing **Ingestion Orchestrator** calls after extraction and before the statement is recorded; the existing **Duplicate Detection Component's** `record_processed` step stores the resulting account reference, type, and closing balance on the `BankStatement` row. | This project already splits small single-purpose steps (Duplicate Detection, Currency Conversion) into their own components called by the orchestrator, rather than growing the orchestrator itself. Account resolution is the same kind of step. |
| **Component identification (API Service)** | Two new components: an **Account Management Component** (list, rename, merge, correct type, set/replace anchor) and a **Balance Component** (balance at a date, balance over a range, discrepancy checks). | Matches the existing granularity (Recurring Payments, Backup Status, and Configuration are each their own component). Writing account/anchor data and computing read-only balances are distinct capabilities with different failure modes, and the Balance Component's core arithmetic is a pure function that is the property-based-testing target (NFR-AB-4), following the project's existing split between a pure decision function and its I/O wrapper (e.g. Currency Conversion's `resolve_conversion_source`). |
| **Component identification (Frontend)** | Extend the single **Frontend SPA** component's responsibilities (Dashboard balance section, account management UI, anchor entry) rather than adding new components. | `components.md` already treats the whole SPA as one component, with every page a responsibility of it, not a component of its own. |
| **Service layer / orchestration** | Balances and the balance chart are **computed on request**, synchronously, inside API Service, by aggregating transactions through their statements to accounts. Nothing is precomputed, materialized, or handed to the Ingestion Worker. | A replaced anchor or an account merge would silently invalidate any precomputed value, and the current data volume (about 6,000 transactions, NFR-AB-5) makes on-demand aggregation comfortably fast. This matches the project's existing split: user-triggered reads and writes are synchronous in API Service; only background work goes through the worker. |
| **Service layer / orchestration** | **Discrepancy checks** (statement closing balance vs the anchor-based balance) are computed on request, not stored. | They depend on the current anchor. If the user corrects a wrong anchor, the warning must disappear on its own (US-13.6), which a stored result could not guarantee. |
| **Component dependencies** | The new API Service components and the extended Ingestion Worker components each depend only on the database. No new edge between `api-service` and `ingestion-worker`. The one possible exception is the FX question below. | The project's one hard architectural rule is that the two services coordinate only through shared rows. |
| **Design patterns / interface style** | Plain REST resource endpoints under new routers, matching existing router conventions (`/transactions`, `/dashboards`, `/categories`, `/ingestion`, ...). Exact paths and DTOs are Functional Design. | The project has one consistent API style already; no reason to introduce another for one feature. |
| **Boundary for correction-preserving matching** | The helper that matches pre-wipe manual corrections to reingested transactions (statement hash, date, amount, description) belongs with the backfill tool, not in the shared ingestion pipeline. | It exists only for the one-time backfill, and putting it in the pipeline would make every future ingestion carry code it never uses. |

## Genuinely open design questions

Two decisions have real tradeoffs that change component boundaries or the user-visible scope, so they are asked rather than decided.

### Question 1
FX rates today are fetched only by the Ingestion Worker (`clients/fx_client.py`, calling exchangerate.host) and cached in `fx_rate_cache` only for the dates of foreign-currency transactions that needed converting. FR-AB-9 needs a rate for the user's requested date, which may be a day with no cached rate. Where should API Service get an as-of-date FX rate from?

(Only matters for savings accounts in a non-SGD currency. SGD accounts never need a rate.)

A) API Service reads only the existing `fx_rate_cache`, using the nearest earlier cached rate for that currency pair; if none exists, the balance is shown as unavailable (FR-AB-9). No new external integration and no new dependency between services. Tradeoff: the rate may be days or weeks old, so converted figures are approximate, and a foreign-currency account with no cached rate at all shows as unavailable.

B) API Service gets its own FX client (calling the same exchangerate.host service) and caches fetched rates into `fx_rate_cache`, so any requested date gets an exact rate. Tradeoff: the first live FX call made from API Service at request time, which needs its own timeout and failure handling; the Ingestion Worker keeps its own client for ingestion.

C) The Ingestion Worker fetches rates on demand: API Service records a request in the database, the worker fetches and caches the rate, and the balance view shows "pending" until it is ready. Tradeoff: preserves "API Service never calls an external FX service", but adds an asynchronous job path and a visible waiting state to every foreign-currency lookup.

D) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 2
Where should the one-time backfill tool (US-13.7: dry run, verified backup, explicit confirmation, wipe, reingest, re-apply corrections, report) live?

A) A single command-line tool run inside the Ingestion Worker container (via `docker compose`). It prints the dry-run report, takes the backup, asks for a typed confirmation, wipes, reingests every PDF in-process through the normal pipeline, re-applies corrections, and prints the completion report. No new API endpoints and no new UI. Tradeoff: no screen to watch, and progress is only visible in the terminal.

B) New API endpoints plus a new Frontend page (Dry run, Confirm, Report), with the actual work executed by the Ingestion Worker through a job row, the same way recategorization jobs run today. Tradeoff: most user-friendly, but the largest scope (touches API Service, Frontend, and the worker), and puts a destructive action behind a button in the app.

C) A command-line tool for the destructive preparation only (dry-run report, verified backup, capture corrections, wipe) and a second command for the finish (re-apply corrections, completion report); in between, you trigger the reingest with the existing "run ingestion" control in the app, so its progress shows on the existing Ingestion page. Tradeoff: two commands to run in the right order, but the reingest itself needs no new code and its progress is visible in the UI.

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Execution Checklist

- [x] Update `components.md` (addendum style, matching the existing "Addendum (date, during stage X)" pattern):
  - [x] Addendum: Statement Extraction Component (Ingestion Worker): new fields
  - [x] New: Account Resolver Component (Ingestion Worker)
  - [x] Addendum: Ingestion Orchestrator Component and Duplicate Detection Component: where the resolver is called and what `record_processed` stores
  - [x] New: Account Management Component (API Service)
  - [x] New: Balance Component (API Service)
  - [x] New: Backfill tool (location per Question 2)
  - [x] Addendum: Frontend SPA: Dashboard balance section, account management UI, anchor entry
  - [x] Addendum: Shared Data Store: Account, balance-anchor entities, new `bank_statements` columns
- [x] Update `component-methods.md` (signatures only, no business rules, those come in Functional Design):
  - [x] Account Resolver: resolve account for a statement
  - [x] Account Management: list, rename, merge, set type, set/replace anchor
  - [x] Balance Component: balance at date (pure core plus I/O wrapper), balance series over a range, discrepancy list
  - [x] Backfill tool: operations per Question 2
  - [x] FX as-of-date lookup: per Question 1
- [x] Update `services.md`: orchestration note (compute on request; discrepancies not stored; resolver runs inside the existing ingestion flow; backfill path per Question 2)
- [x] Update `component-dependency.md`: new edges (API Service components to Database only, resolver to Database only; Question 1's outcome determines whether any new edge to an FX service exists); confirm no new edge between the two services
- [x] Regenerate `application-design.md` (consolidated doc) to include all of the above
- [x] Validate design completeness and consistency against FR-AB-1..17 and US-13.1..13.7 (every requirement and story lands on a named component)
- [x] Update `aidlc-state.md`
