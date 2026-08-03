# NFR Requirements Plan — Unit 2: API Service

**Input**: `aidlc-docs/construction/api-service/functional-design/` (approved)

## NFR Category Assessment

| Category | Assessment |
|---|---|
| Scalability | N/A — single personal user, no concurrent-user load to plan for |
| Performance | Addressed via Unit 1's indexing strategy + AR-8 pagination bounds; no additional tuning needed at this scale |
| Availability | N/A — Resiliency Baseline extension opted out (requirements.md NFR-5.3) |
| Security | Baseline only: JWT secret + login credentials via env vars (NFR-4.1); no rate-limiting/brute-force protection added since the Security Baseline extension was opted out and this is a personal, non-internet-exposed app |
| Tech Stack Selection | **Real decisions**: web framework confirmation, API docs exposure — questions below. Language (Python), ORM (SQLAlchemy), and migration tooling (Alembic) are already locked in from Unit 1 and simply reused here. |
| Reliability | Handled at the business-logic level already (AR-6 single-active-run, clean error responses per business-rules.md) — no additional pattern needed |
| Maintainability | PBT framework selection remains deferred to Unit 3 (where the clearest pure functions live); once chosen there, it will also apply to any of Unit 2's pure functions (e.g., the filter-to-SQL-clause builder) per Partial PBT mode |
| Usability | N/A — this unit has no UI (Frontend is Unit 4) |

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (web framework confirmation, API docs exposure) — FastAPI, docs enabled
- [x] Step 2: Generate `nfr-requirements.md`
- [x] Step 3: Generate `tech-stack-decisions.md`

## Clarifying Questions

### Question 1 — Web Framework
Requirements Analysis floated "Python/FastAPI" as an illustrative example only, not a locked decision. Confirming now: should Unit 2 use FastAPI?

A) **FastAPI** — async-native (fits the non-blocking ingestion-trigger endpoint well), automatic request/response validation from the DTOs already defined in `domain-entities.md` (via Pydantic), auto-generated OpenAPI schema

B) **Flask** — simpler/more minimal, synchronous by default, larger ecosystem of examples, but request/response validation and async support both need extra libraries bolted on

X) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 2 — Interactive API Docs Exposure
FastAPI can auto-serve interactive API documentation (Swagger UI at `/docs`, ReDoc at `/redoc`) generated from the endpoint definitions. Should this be enabled?

A) **Enabled** — useful for you to explore/test the API directly during and after development; the docs pages themselves are unauthenticated by default (though the actual data endpoints they document still require the JWT per AR-1), and this service isn't exposed to the public internet

B) **Disabled in this deployment** — avoids exposing API shape/schema information on an unauthenticated page at all, even though the app isn't internet-facing

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
