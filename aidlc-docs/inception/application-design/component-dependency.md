# Component Dependencies — Bank Transaction Insights App

## Dependency Matrix

| Component | Depends On | Communication Pattern |
|---|---|---|
| Frontend SPA | API Service (Auth, Transaction Mgmt, Dashboard, Ingestion Trigger, Configuration) | REST/HTTP (JSON), Question 4 = A |
| Auth Component | Shared DB (users table) | In-process DB query |
| Transaction Management Component | Shared DB (transactions table); Ingestion Trigger & Status Component (to enqueue recategorize job) | In-process DB query; in-process method call (same service) |
| Dashboard/Insights Component | Shared DB (transactions, fx-rate-cache tables) | In-process DB query |
| Ingestion Trigger & Status Component | Shared DB (ingestion-runs/jobs table) | In-process DB query (writes `queued` rows; reads status rows) |
| Configuration Component | Shared DB (categories table); validates against transactions table for in-use check; `setting_changes` table *(added 2026-08-16)*; read-only query of `ingestion_runs`/`recategorization_jobs` for busy/idle *(added 2026-08-16, no new table)*; shared override-settings volume, write side *(added 2026-08-16)* | In-process DB query; filesystem write (new volume, not a DB query) |
| Recategorization Review Component *(added 2026-08-02, extended 2026-08-16)* | Shared DB (recategorization-proposals table; `categorization_disagreements` table *(added 2026-08-16)*; transactions table on approval/resolution) | In-process DB query — no dependency on Ingestion Worker Service |
| Backup Status Component *(added 2026-08-08)* | Shared DB (`backup_runs` table) | In-process DB query — no dependency on Ingestion Worker Service |
| Recurring Payments Component *(added 2026-08-08)* | Shared DB (recurring-payments register, match, and detection-suggestion tables; transactions table for match display context) | In-process DB query — no dependency on Ingestion Worker Service |
| Background Activity Component *(added 2026-08-18)* | Shared DB (`ingestion_runs`, `recategorization_jobs` tables — read-only) | In-process DB query — no dependency on Ingestion Worker Service |
| Account Management Component *(added 2026-10-02)* | Shared DB (`accounts`, balance-anchor tables; `bank_statements` account reference on merge) | In-process DB query — no dependency on Ingestion Worker Service |
| Balance Component *(added 2026-10-02)* | Shared DB (`accounts`, balance-anchor, `bank_statements`, `transactions`, and `fx_rate_cache` tables — all **read-only**); Account Management Component's data only via the DB, not by call | In-process DB query — no dependency on Ingestion Worker Service, and no external FX call (Question 1 = A, cache-only) |
| Duplicate Review Component *(added 2026-10-03)* | Shared DB (remembered-files, comparisons, duplicate-pairs, removal-jobs, scan-state tables — read and write; `bank_statements`, `statement_accounts`, `transactions` and the transaction-dependent tables — **read-only**, for correction counts and the removal preview) | In-process DB query — no dependency on Ingestion Worker Service, and **no dependency on the vector store** (NFR-PD-4) |
| Ingestion Orchestrator Component | Drive Connector, Duplicate Detection, Statement Extraction, Account Resolver *(added 2026-10-02)*, Categorization Engine, Currency Conversion (all same service); Shared DB (ingestion-runs/jobs table, transactions table) | In-process method calls; in-process DB query |
| Backup Manager Component *(added 2026-08-08)* | Drive Connector Component (same service); Shared DB (transactions table for export, `backup_runs` table for status) | In-process method calls; in-process DB query |
| Recurring Payment Manager Component *(added 2026-08-08)* | Categorization Engine's similarity matcher (same service, reused per NFR-1); Shared DB (transactions table, recurring-payments register/match/detection-suggestion tables); Vector Store Client Component *(added 2026-08-11)* | In-process method calls; in-process DB query |
| Drive Connector Component | Google Drive API (external) — read scopes (existing) + write scopes (new, for the dedicated backup folder) | OAuth 2.0 + REST (external) |
| Duplicate Detection Component | Shared DB (processed-statements table) | In-process DB query |
| Statement Extraction Component | OCR engine/library (external or embedded); LLM API (external, for layout-adaptive parsing) | Library call; REST (external) |
| Account Resolver Component *(added 2026-10-02)* | Shared DB (`accounts` table — read and write). No external dependency. | In-process DB query; called in-process by the Ingestion Orchestrator |
| Probable Duplicate Detector Component *(added 2026-10-03)* | Shared DB (`bank_statements`, `statement_accounts`, `transactions` — read; remembered-files, comparisons, duplicate-pairs, scan-state tables — read and write); the Account Resolver's pure bank-key normalizer (same service); the settings (detection on/off, match ratio, small-statement minimum). No external call. | In-process DB query; in-process function call |
| Statement Removal Handler Component *(added 2026-10-03)* | Shared DB (removal-jobs, duplicate-pairs, remembered-files — read and write; `bank_statements`, `statement_accounts`, `transactions` and every transaction-dependent table — delete); Vector Store Client Component (same service) | In-process DB query; in-process method call. Invoked only by `poll_once()`, never by the API Service |
| Backfill Tool Component *(added 2026-10-02)* | Ingestion Orchestrator Component's `processRun` (same package, reused not copied); Drive Connector Component (same package); Shared DB (statements, transactions, and their dependent tables — read, delete, and re-insert via the normal ingestion path); backup target (mechanism open — Functional Design) | Command-line entry point; in-process method calls; in-process DB query |
| Categorization Engine Component | Shared DB (transactions table, for similarity search; `transactions.llm_suggested_category_id` *(added 2026-08-16)*; `categorization_disagreements` table, write-only *(added 2026-08-16)*); LLM API (external); Vector Store Client Component *(added 2026-08-11)* | In-process DB query; REST (external); in-process method call |
| Currency Conversion Component | Shared DB (fx-rate-cache table); FX Rate API (external) | In-process DB query; REST (external) |
| Vector Store Client Component *(added 2026-08-11)* | Vector DB (external, dedicated service — not the Shared DB) | REST/gRPC (external, product TBD at NFR Requirements) |
| Embedding Manager Component *(added 2026-08-11)* | oMLX (external, user-managed local endpoint, config-supplied URL); Vector Store Client Component (same service); Shared DB (`transactions.embedding_status`) | REST (external); in-process method call; in-process DB query |
| Configuration Loading *(both services, added 2026-08-16, Configurable Application Settings feature — cross-cutting, not a business-logic component)* | Shared override-settings volume, read side — both services' `Settings` classes read it via `env_file` at process start | Filesystem read at startup, not a DB query, not a call to the other service |
| Dataset Curator Component *(added 2026-08-17, Model Training unit)* | Shared DB (transactions, recategorization_proposals, categorization_disagreements tables) — **read-only** | Direct DB query via the shared `transactagent_db` package, not a new data-access layer |
| Fine-Tuning Trainer Component *(added 2026-08-17, Model Training unit)* | Dataset Curator Component's output (same unit, filesystem hand-off); HuggingFace Hub (external, base model download); ClearML SaaS (external, run tracking); the oMLX server (`evaluate()` only, for the agreement-rate comparison — see Functional Design MTR-7 correction: an independent HTTP call replicating the live prompt template, not a call into API Service/Ingestion Worker Service code, since no such endpoint exists) | Filesystem read; REST (external) x3, all direct HTTP, no dependency on either existing service |

*Addendum (2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: the rows above are new; these existing rows gain dependencies and are otherwise unchanged. **Frontend SPA** also depends on the Duplicate Review Component (REST). **Ingestion Trigger & Status Component** and **Configuration Component**: no new dependency (an extra DTO field set; three more catalog entries). **Duplicate Detection Component** also reads the remembered-files table. **Ingestion Orchestrator Component** also depends on the Probable Duplicate Detector Component (same service, in-process). **Vector Store Client Component**: no new dependency (a new delete operation; its one new caller is the Statement Removal Handler). **Backfill Tool Component** also depends on the Probable Duplicate Detector Component (`check-duplicates`, dry-run listing) and on the Shared DB's remembered-files and duplicate-pairs tables (pre-registration, clearing resolved pairs, backup and restore). **Nothing new depends on Google Drive, the LLM, or oMLX.**

## Communication Patterns Summary

- **Frontend ↔ API Service**: REST over HTTP, synchronous request/response
- **API Service ↔ Ingestion Worker Service**: **No direct call** — fully decoupled via the shared DB's run/job table (see `services.md` — Cross-Service Coordination). *Addendum (2026-08-02)*: the new Recategorization Review Component holds to this same rule — it reads/writes proposal rows the Worker wrote, never calling it directly. *Addendum (2026-08-08)*: the new Backup Status Component holds to the same rule — it only reads `backup_runs` rows the Worker's Backup Manager wrote. *Addendum (2026-08-08)*: the new Recurring Payments Component holds to the same rule too — match/detection-suggestion *creation* is exclusively the Worker's Recurring Payment Manager; API Service only reads them and writes resolution fields (approved/rejected/dismissed/added) on rows the Worker already created.
- **Within API Service**: in-process method calls between components (modular monolith internally, per this service's own boundary)
- **Within Ingestion Worker Service**: in-process method calls, orchestrated by the Ingestion Orchestrator
- **Both services ↔ Shared DB**: direct DB connections; no ORM/library is shared between the two services' codebases — they coordinate only through the documented schema (a data contract), consistent with Question 1 = B (separate, independently deployable services)
- **Ingestion Worker Service ↔ External APIs**: Google Drive (OAuth), LLM provider (categorization + extraction assistance), FX Rate API, OCR (library or external API — confirmed in NFR Requirements)
- **Ingestion Worker Service ↔ Vector DB** *(added 2026-08-11)*: the new Vector Store Client Component only — a separate, dedicated datastore from the Shared DB. **API Service never connects to it** — holds the same "no direct access to a Worker-owned datastore" rule as `backup_runs`/proposals/recurring-payments tables (all of which the API Service reaches via its own Shared-DB connection, not by touching a Worker-internal store).
- **Ingestion Worker Service ↔ oMLX** *(added 2026-08-11)*: the new Embedding Manager Component only, and only for the async/batched storage-time embedding computation (`processNextEmbeddingBatch`) — plus the Categorization Engine/Recurring Payment Manager's query-time transient embedding calls (both addended above), which also go through `EmbeddingManager.computeEmbedding()`, not a second, separate client. User-managed, host-native, config-pointed — not part of `docker-compose` (NFR-5).
- **API Service ↔ Ingestion Worker Service** *(addendum, 2026-08-16)*: the extended Recategorization Review Component holds to the same "no direct call" rule for the new `categorization_disagreements` table too — it only reads/resolves rows the Worker's Categorization Engine already wrote, same as every other review-style component before it.
- **API Service ↔ Ingestion Worker Service** *(addendum, 2026-08-16, Configurable Application Settings feature)*: a second, genuinely new coordination channel is introduced — a shared, non-secret override-settings file on a new Docker volume bind-mounted into both containers (Configuration Component writes; both services' `Settings` classes read via `env_file` at their own next startup). Still not a "direct call" in the sense this rule means — no RPC, no synchronous request/response, no availability coupling at write time — see `services.md`'s new "Cross-Service Coordination: Settings Override File" section for the full reasoning. Busy/idle status (FR-CAS-7) deliberately does **not** use this new channel — it's answered by a Shared DB query instead (Key Design Resolution 2), so the original DB-only coordination rule stays fully intact for that piece.
- **Model Training ↔ Shared DB** *(addendum, 2026-08-17, Categorization Model Fine-Tuning feature)*: the first consumer with a **read-only** relationship to the Shared DB — no writer/reader pairing like every entry above. Connects directly (reusing the `transactagent_db` package), not through either existing service.
- **Model Training ↔ API Service / Ingestion Worker Service**: **no dependency in either direction, full stop** — corrected during Functional Design (MTR-7): `evaluate()`'s "compare against the live model" step does not call into either service's code or any endpoint (none exists for on-demand classification) — it independently replicates WR-34's prompt template and calls the same oMLX server directly. Nothing on the API Service/Ingestion Worker Service side is aware Model Training exists, and nothing in Model Training imports or calls either service's package.
- **Model Training ↔ External Services** *(new)*: HuggingFace Hub (download the base model), ClearML SaaS (run tracking), and the oMLX server (`evaluate()`'s live-model comparison, MTR-7 — the same server `ingestion-worker` talks to, but reached independently, not through it) — three external dependencies, all isolated to this one unit (NFR-CFT-1/NFR-CFT-3).
- **API Service ↔ Ingestion Worker Service** *(addendum, 2026-08-18, Background Process Visibility feature)*: the new Background Activity Component holds to the same "no direct call" rule as every read-only component above — it only reads `ingestion_runs`/`recategorization_jobs` rows the Worker's Ingestion Orchestrator/Categorization Engine already write, polled frequently by the Frontend rather than by the Worker pushing anything.
- **API Service ↔ Ingestion Worker Service** *(addendum, 2026-10-02, Account Balance at a Point in Time feature)*: the new Account Management and Balance Components hold to the same "no direct call" rule. The Account Resolver (Worker) creates `accounts` rows and the Account Management Component (API) edits them, with no call in either direction. The Balance Component reads the `fx_rate_cache` rows the Worker's Currency Conversion Component wrote and **never calls an external FX service** (Question 1 = A), so API Service gains no new external dependency; the tradeoff, accepted explicitly, is that an as-of-date rate is the nearest *earlier* cached one (marked approximate) or unavailable.
- **Backfill Tool** *(addendum, 2026-10-02)*: a command-line entry point inside the Ingestion Worker Service's package and image, not a new service or container. It adds no edge to the diagram below — it reuses the Worker's own Shared DB and Google Drive connections — and offers no REST surface to the Frontend or API Service (Question 2 = A).

- **API Service ↔ Ingestion Worker Service** *(addendum, 2026-10-03, Probable Duplicate Statement Detection feature — Epic 14)*: the new Duplicate Review Component holds to the same "no direct call" rule. It reads pairs and comparisons the worker's Probable Duplicate Detector wrote and writes decisions (override, dismissal, re-check) and removal jobs as rows; the worker's Statement Removal Handler reads and executes them. Removal is the one flow that needs the Vector DB, so it is executed on the worker's side of the line, which is the only reason it is a job rather than a synchronous delete.
- **Ingestion Worker Service ↔ Vector DB** *(addendum, 2026-10-03)*: the Statement Removal Handler becomes a second caller of the Vector Store Client Component (alongside the Categorization Engine, Recurring Payment Manager, and Embedding Manager), using its new delete operation. **API Service still never connects to the Vector DB.**
- **Backfill Tool** *(addendum, 2026-10-03)*: still no new edge. It also calls the Probable Duplicate Detector in-process and writes remembered-file records through the Shared DB connection it already has.

## Data Flow Diagram

```
          +---------------------------+
          | Frontend SPA              |
          +---------------------------+
                        |
                        | REST/HTTP
                        v
          +---------------------------+
          | API Service               |
          | - Auth                    |
          | - Transaction Mgmt        |
          | - Dashboard/Insights      |
          | - Ingestion Trigger       |
          | - Configuration           |
          | - Recateg. Review         |
          | - Backup Status           |
          | - Recur. Payments         |
          | - Account Mgmt            |
          | - Balance                 |
          | - Duplicate Review        |
          +---------------------------+
                        |
                        v
          +---------------------------+
          | Shared DB                 |
          | - users                   |
          | - transactions            |
          |   (+embedding_status)     |
          | - processed-stmts         |
          | - statement-accounts      |
          | - categories              |
          | - ingestion-runs          |
          | - fx-rate-cache           |
          | - recateg-proposals       |
          | - backup-runs             |
          | - recur-payments          |
          | - categ-disagreements     |
          | - setting-changes         |
          | - accounts                |
          | - balance-anchors         |
          | - remembered-files        |
          | - dup-comparisons         |
          | - dup-pairs               |
          | - removal-jobs            |
          | - dup-scan-state          |
          +---------------------------+
                        ^
                        |
          +---------------------------+
          | Ingestion Worker Svc      |
          | - Orchestrator            |
          | - Drive Connector         |
          | - Duplicate Detect        |
          | - Statement Extract       |
          | - Categorization          |
          | - Currency Convert        |
          | - Backup Manager          |
          | - Recur. Pmt Mgr          |
          | - Embedding Mgr           |
          | - Vector Store Client     |
          | - Account Resolver        |
          | - Prob. Dup Detector      |
          | - Removal Handler         |
          | - Backfill Tool (CLI)     |
          +---------------------------+
                    |         |
                    |         +----------------------------+
                    v                                       v
          +---------------------------+       +-----------------------------+
          | External APIs             |       | Vector DB (new)             |
          | - Google Drive (OAuth)    |       | - transaction embeddings    |
          | - LLM API                 |       | - recur-payment embeddings  |
          | - FX Rate API             |       +-----------------------------+
          | - oMLX (local, external)  |
          +---------------------------+
```

**Text validation**: All lines are ASCII-only (`+ - | v ^`), no unicode box-drawing characters; every box's border and content lines are a consistent width within that box (programmatically verified), consistent with `common/ascii-diagram-standards.md`. Re-verified after the 2026-08-08 Nightly Transaction Backup addenda (Backup Status, Backup Manager, backup-runs lines), again after the 2026-08-08 Recurring Payments addenda (Recur. Payments, Recur. Pmt Mgr, recur-payments lines), again after the 2026-08-11 Local Embedding-Based Semantic Similarity addenda (Embedding Mgr, Vector Store Client, oMLX, and the new Vector DB box — the Worker now branches to two downstream boxes instead of one, per `ascii-diagram-standards.md`'s Horizontal Flow pattern), again after the 2026-08-16 Matching Precision Refinement addendum (`- categ-disagreements` line added to the Shared DB box; no new component box needed — `Transaction.llm_suggested_category_id` is a field addition, not a new box; every content line still 39 chars, matching every existing line in that box, verified programmatically above), and again after the 2026-08-16 Configurable Application Settings addendum (`- setting-changes` line added to the Shared DB box, still 39 chars; the genuinely new coordination channel is deliberately shown as its own small diagram below, not merged into this one, since two of its three participants — API Service and Ingestion Worker Svc — are already separated by the Shared DB box in this vertical layout, and forcing a diagonal/bypass arrow through an existing, already-verified diagram was judged higher-risk than a second, self-contained one). Re-verified after the 2026-10-03 Probable Duplicate Statement Detection addenda (Duplicate Review, remembered-files / dup-comparisons / dup-pairs / removal-jobs / dup-scan-state, Prob. Dup Detector, Removal Handler lines): every box is still the same width on every line, ASCII-only.

### Data Flow Diagram: Settings Override Channel *(new, 2026-08-16, Configurable Application Settings feature)*

The genuinely new, non-DB coordination channel from `services.md`'s "Cross-Service Coordination: Settings Override File" section, shown separately from the main diagram above for the reason stated in that section's Text validation note:

```
+-----------------------------+
| API Service                 |
| Configuration Component     |
+-----------------------------+
              |
              | write, updateSetting()
              v
+-----------------------------+
| Shared Config Volume (new)  |
| - override-settings file    |
+-----------------------------+
              ^
              | read at own startup (env_file)
              |
+-----------------------------+
| Ingestion Worker Svc        |
| Settings (config.py)        |
+-----------------------------+
```

**Text validation**: All lines ASCII-only; all 3 boxes are a consistent 31 characters wide (programmatically verified). Busy/idle status (FR-CAS-7) is intentionally absent from this diagram — it flows through the existing Shared DB (main diagram above), not this channel, per Key Design Resolution 2.

### Data Flow Diagram: Model Training Unit *(new, 2026-08-17, Categorization Model Fine-Tuning feature)*

Shown separately rather than merged into the main diagram above — Model Training isn't part of either existing service's request/response or Run/Job Queue flow, and is the first component with a purely **read-only** relationship to the Shared DB:

```
+---------------------------+
| Model Training (new unit) |
| - Dataset Curator         |
| - Fine-Tuning Trainer     |
+---------------------------+
              |
              | read-only query (transactagent_db)
              v
+-------------+
| Shared DB   |
| (read-only) |
+-------------+
```

**Text validation**: All lines ASCII-only; both boxes internally consistent width (29 and 15 characters respectively, programmatically verified). Not shown as boxes: Model Training's three other dependencies — HuggingFace Hub (base model download), ClearML SaaS (run tracking), and the oMLX server (`evaluate()`'s live-model comparison, MTR-7 correction — reached directly, not through Ingestion Worker Service) — all outbound REST calls to external/local-network services, already fully captured in the Dependency Matrix and Communication Patterns Summary above without needing further boxes.
