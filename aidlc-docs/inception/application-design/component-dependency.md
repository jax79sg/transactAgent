# Component Dependencies — Bank Transaction Insights App

## Dependency Matrix

| Component | Depends On | Communication Pattern |
|---|---|---|
| Frontend SPA | API Service (Auth, Transaction Mgmt, Dashboard, Ingestion Trigger, Configuration) | REST/HTTP (JSON), Question 4 = A |
| Auth Component | Shared DB (users table) | In-process DB query |
| Transaction Management Component | Shared DB (transactions table); Ingestion Trigger & Status Component (to enqueue recategorize job) | In-process DB query; in-process method call (same service) |
| Dashboard/Insights Component | Shared DB (transactions, fx-rate-cache tables) | In-process DB query |
| Ingestion Trigger & Status Component | Shared DB (ingestion-runs/jobs table) | In-process DB query (writes `queued` rows; reads status rows) |
| Configuration Component | Shared DB (categories table); validates against transactions table for in-use check | In-process DB query |
| Recategorization Review Component *(added 2026-08-02)* | Shared DB (recategorization-proposals table; transactions table on approval) | In-process DB query — no dependency on Ingestion Worker Service |
| Ingestion Orchestrator Component | Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion (all same service); Shared DB (ingestion-runs/jobs table, transactions table) | In-process method calls; in-process DB query |
| Drive Connector Component | Google Drive API (external) | OAuth 2.0 + REST (external) |
| Duplicate Detection Component | Shared DB (processed-statements table) | In-process DB query |
| Statement Extraction Component | OCR engine/library (external or embedded); LLM API (external, for layout-adaptive parsing) | Library call; REST (external) |
| Categorization Engine Component | Shared DB (transactions table, for similarity search); LLM API (external) | In-process DB query; REST (external) |
| Currency Conversion Component | Shared DB (fx-rate-cache table); FX Rate API (external) | In-process DB query; REST (external) |

## Communication Patterns Summary

- **Frontend ↔ API Service**: REST over HTTP, synchronous request/response
- **API Service ↔ Ingestion Worker Service**: **No direct call** — fully decoupled via the shared DB's run/job table (see `services.md` — Cross-Service Coordination). *Addendum (2026-08-02)*: the new Recategorization Review Component holds to this same rule — it reads/writes proposal rows the Worker wrote, never calling it directly.
- **Within API Service**: in-process method calls between components (modular monolith internally, per this service's own boundary)
- **Within Ingestion Worker Service**: in-process method calls, orchestrated by the Ingestion Orchestrator
- **Both services ↔ Shared DB**: direct DB connections; no ORM/library is shared between the two services' codebases — they coordinate only through the documented schema (a data contract), consistent with Question 1 = B (separate, independently deployable services)
- **Ingestion Worker Service ↔ External APIs**: Google Drive (OAuth), LLM provider (categorization + extraction assistance), FX Rate API, OCR (library or external API — confirmed in NFR Requirements)

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
          +---------------------------+
                        |
                        v
          +---------------------------+
          | Shared DB                 |
          | - users                   |
          | - transactions            |
          | - processed-stmts         |
          | - categories              |
          | - ingestion-runs          |
          | - fx-rate-cache           |
          | - recateg-proposals       |
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
          +---------------------------+
                        |
                        v
          +---------------------------+
          | External APIs             |
          | - Google Drive (OAuth)    |
          | - LLM API                 |
          | - FX Rate API             |
          +---------------------------+
```

**Text validation**: All lines are ASCII-only (`+ - | v ^`), no unicode box-drawing characters; every box's border and content lines are exactly 29 characters wide (programmatically verified), consistent with `common/ascii-diagram-standards.md`.
