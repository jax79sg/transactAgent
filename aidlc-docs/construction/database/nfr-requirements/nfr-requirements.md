# NFR Requirements — Unit 1: Database

## Assessed Categories

| Category | Requirement | Rationale |
|---|---|---|
| Scalability | No specific target; schema must comfortably handle low-thousands of transaction rows/year, tens of ingestion runs/year | Single personal user (NFR-1.2 context); Medium risk assessment in execution-plan.md already notes contained blast radius |
| Performance | Dashboard queries (FR-8) should return well within interactive UI expectations (sub-second) for this data volume | Achieved via indexing (see below), not special infrastructure |
| Availability | No uptime SLA | Personal local deployment; Resiliency Baseline extension opted out (requirements.md NFR-5.3) |
| Security | DB credentials supplied via environment variables at container startup (NFR-4.1); no credentials in migration files or source control | Baseline secret hygiene applies regardless of the opted-out Security extension |
| Reliability | Partial-failure isolation already modeled at the schema/state-machine level (business-logic-model.md) — a failed `IngestionRunFile` never blocks other files or corrupts committed `Transaction` rows (NFR-2.2) | N/A beyond what functional design already captured |
| Maintainability | PBT framework selection (PBT-09) deferred to Unit 3 (Ingestion Worker Service) — Unit 1 has no pure business-logic functions, only schema/migrations | Consistent with Partial PBT mode (requirements.md NFR-5.2) |
| Usability | N/A | No UI in this unit |

## Tech Stack Decisions (Summary — see tech-stack-decisions.md for detail)

- **Database engine**: PostgreSQL (Question 1 = A)
- **Migration tooling**: Alembic (Python), ORM-native, tied to the API Service's framework (Question 2 = B)
- **Backend language (project-wide, decided here due to Q2=B's dependency)**: Python — carried into Unit 2 and Unit 3 NFR Requirements

## Indexing Strategy (decided directly — standard practice, not a user decision)

- `transactions(transaction_date)` — supports date-range filtering (FR-7.1) and dashboard time-series queries (FR-8)
- `transactions(category_id)` — supports category filter/group (FR-7.1/7.2)
- `transactions(bank_name)` — supports bank filter/group
- `transactions(bank_statement_id)` — FK lookup, traceability (FR-4.2)
- `bank_statements(pdf_content_hash)` — UNIQUE index, enforces BR-3 and makes duplicate-check lookups fast (FR-3.2, this is the hot path on every ingestion run)
- `ingestion_run_files(ingestion_run_id)` — FK lookup for run drill-down (US-1.5)
- `fx_rate_cache(from_currency, to_currency, rate_date)` — UNIQUE index, enforces BR-7 and is the cache lookup key (FR-10.3/10.4)
