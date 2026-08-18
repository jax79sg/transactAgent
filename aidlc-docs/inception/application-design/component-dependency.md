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
| Ingestion Orchestrator Component | Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion (all same service); Shared DB (ingestion-runs/jobs table, transactions table) | In-process method calls; in-process DB query |
| Backup Manager Component *(added 2026-08-08)* | Drive Connector Component (same service); Shared DB (transactions table for export, `backup_runs` table for status) | In-process method calls; in-process DB query |
| Recurring Payment Manager Component *(added 2026-08-08)* | Categorization Engine's similarity matcher (same service, reused per NFR-1); Shared DB (transactions table, recurring-payments register/match/detection-suggestion tables); Vector Store Client Component *(added 2026-08-11)* | In-process method calls; in-process DB query |
| Drive Connector Component | Google Drive API (external) — read scopes (existing) + write scopes (new, for the dedicated backup folder) | OAuth 2.0 + REST (external) |
| Duplicate Detection Component | Shared DB (processed-statements table) | In-process DB query |
| Statement Extraction Component | OCR engine/library (external or embedded); LLM API (external, for layout-adaptive parsing) | Library call; REST (external) |
| Categorization Engine Component | Shared DB (transactions table, for similarity search; `transactions.llm_suggested_category_id` *(added 2026-08-16)*; `categorization_disagreements` table, write-only *(added 2026-08-16)*); LLM API (external); Vector Store Client Component *(added 2026-08-11)* | In-process DB query; REST (external); in-process method call |
| Currency Conversion Component | Shared DB (fx-rate-cache table); FX Rate API (external) | In-process DB query; REST (external) |
| Vector Store Client Component *(added 2026-08-11)* | Vector DB (external, dedicated service — not the Shared DB) | REST/gRPC (external, product TBD at NFR Requirements) |
| Embedding Manager Component *(added 2026-08-11)* | oMLX (external, user-managed local endpoint, config-supplied URL); Vector Store Client Component (same service); Shared DB (`transactions.embedding_status`) | REST (external); in-process method call; in-process DB query |
| Configuration Loading *(both services, added 2026-08-16, Configurable Application Settings feature — cross-cutting, not a business-logic component)* | Shared override-settings volume, read side — both services' `Settings` classes read it via `env_file` at process start | Filesystem read at startup, not a DB query, not a call to the other service |
| Dataset Curator Component *(added 2026-08-17, Model Training unit)* | Shared DB (transactions, recategorization_proposals, categorization_disagreements tables) — **read-only** | Direct DB query via the shared `transactagent_db` package, not a new data-access layer |
| Fine-Tuning Trainer Component *(added 2026-08-17, Model Training unit)* | Dataset Curator Component's output (same unit, filesystem hand-off); HuggingFace Hub (external, base model download); ClearML SaaS (external, run tracking); the oMLX server (`evaluate()` only, for the agreement-rate comparison — see Functional Design MTR-7 correction: an independent HTTP call replicating the live prompt template, not a call into API Service/Ingestion Worker Service code, since no such endpoint exists) | Filesystem read; REST (external) x3, all direct HTTP, no dependency on either existing service |

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
          +---------------------------+
                        |
                        v
          +---------------------------+
          | Shared DB                 |
          | - users                   |
          | - transactions            |
          |   (+embedding_status)     |
          | - processed-stmts         |
          | - categories              |
          | - ingestion-runs          |
          | - fx-rate-cache           |
          | - recateg-proposals       |
          | - backup-runs             |
          | - recur-payments          |
          | - categ-disagreements     |
          | - setting-changes         |
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

**Text validation**: All lines are ASCII-only (`+ - | v ^`), no unicode box-drawing characters; every box's border and content lines are a consistent width within that box (programmatically verified), consistent with `common/ascii-diagram-standards.md`. Re-verified after the 2026-08-08 Nightly Transaction Backup addenda (Backup Status, Backup Manager, backup-runs lines), again after the 2026-08-08 Recurring Payments addenda (Recur. Payments, Recur. Pmt Mgr, recur-payments lines), again after the 2026-08-11 Local Embedding-Based Semantic Similarity addenda (Embedding Mgr, Vector Store Client, oMLX, and the new Vector DB box — the Worker now branches to two downstream boxes instead of one, per `ascii-diagram-standards.md`'s Horizontal Flow pattern), again after the 2026-08-16 Matching Precision Refinement addendum (`- categ-disagreements` line added to the Shared DB box; no new component box needed — `Transaction.llm_suggested_category_id` is a field addition, not a new box; every content line still 39 chars, matching every existing line in that box, verified programmatically above), and again after the 2026-08-16 Configurable Application Settings addendum (`- setting-changes` line added to the Shared DB box, still 39 chars; the genuinely new coordination channel is deliberately shown as its own small diagram below, not merged into this one, since two of its three participants — API Service and Ingestion Worker Svc — are already separated by the Shared DB box in this vertical layout, and forcing a diagonal/bypass arrow through an existing, already-verified diagram was judged higher-risk than a second, self-contained one).

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
