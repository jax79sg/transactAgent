# Tech Stack Decisions — Unit 1: Database

| Decision | Choice | Rationale |
|---|---|---|
| Database engine | **PostgreSQL 16** (or latest stable at build time) | Question 1 = A — concurrent multi-process access from 2 backend services; strong native support for `DECIMAL`, `ENUM`, `CHECK` constraints (needed for BR-1–BR-13); mature Docker image (`postgres:16-alpine`) |
| Migration tooling | **Alembic** | Question 2 = B (ORM-native, tied to API Service's framework) — Alembic is the standard migration tool for SQLAlchemy-based Python projects |
| ORM / schema definition | **SQLAlchemy** (used by both Unit 2 and Unit 3 to define/apply the same models) | Pairs with Alembic; both backend units import the same SQLAlchemy model definitions from this unit's package so schema stays single-sourced despite being 2 separate deployables |
| Backend language (project-wide) | **Python 3.12+** | Decided here because Question 2 = B made migration tooling depend on it; matches Requirements Analysis Q11's approved example stack; strong fit for PDF/OCR/LLM-heavy processing in Unit 3 |

## Consequence for Code Organization

Per `unit-of-work.md`, Unit 1's `database/` directory will contain:
- SQLAlchemy model definitions (the single source of truth for the schema described in `domain-entities.md`)
- Alembic migration scripts (versioned, auto-generated from model changes)
- A small packaging setup so Units 2 and 3 can both depend on this package (e.g., installed as a local/editable Python package within the monorepo) rather than duplicating model definitions

This satisfies Question 2's intent (ORM-native tooling) while still avoiding duplicating the schema definition across Units 2 and 3 — they share the model code, not just the migration files.

## Carried Forward to Units 2 and 3

Unit 2 (API Service) and Unit 3 (Ingestion Worker Service) NFR Requirements stages will confirm **Python** as their implementation language (not re-litigated as an open question) but still independently decide their own frameworks (e.g., FastAPI for Unit 2), libraries, and any unit-specific NFRs.
