# NFR Requirements — Unit 2: API Service

## Assessed Categories

| Category | Requirement | Rationale |
|---|---|---|
| Scalability | No target | Single personal user |
| Performance | Sub-second response for filter/list/dashboard endpoints at personal-scale data volumes | Achieved via Unit 1's indexes + AR-8 pagination bounds, no extra infra |
| Availability | No SLA | Resiliency Baseline extension opted out |
| Security | JWT secret and login credentials via env vars (NFR-4.1); no rate limiting/brute-force protection | Security Baseline extension opted out; app is not internet-exposed (confirmed in Infrastructure Design — no host port planned to be publicly reachable) |
| Reliability | Clean, typed error responses for all business-rule violations (AR-1..AR-10) rather than raw 500s | Already captured in business-rules.md |
| Maintainability | PBT framework selection deferred to Unit 3; Partial PBT mode will apply here too once chosen, to the filter-to-SQL-clause builder (a pure function) | Consistent with requirements.md NFR-5.2 |
| Usability | N/A | No UI in this unit |

## Tech Stack Decisions (Summary — see tech-stack-decisions.md)

- **Web framework**: FastAPI (Question 1 = A)
- **API docs**: Swagger UI (`/docs`) and ReDoc (`/redoc`) enabled (Question 2 = A)
- **Language/ORM/migrations**: Python 3.12+, SQLAlchemy, Alembic — reused from Unit 1's NFR Requirements (not re-decided)
