# Tech Stack Decisions — Unit 2: API Service

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Reused from Unit 1 |
| Web framework | **FastAPI** | Question 1 = A — async-native, Pydantic-based request/response validation maps directly onto the DTOs in `domain-entities.md`, auto-generated OpenAPI schema |
| ASGI server | **Uvicorn** | Standard FastAPI production server |
| Data validation | **Pydantic v2** | Ships with FastAPI; used for all request/response DTO models |
| ORM | SQLAlchemy (via `transactagent_db` package from Unit 1) | Reused, not duplicated |
| Migrations | Alembic (via `transactagent_db.migrate.run_migrations_with_lock()`) | Reused from Unit 1 |
| Auth | **PyJWT** for token signing/verification; **bcrypt** (direct, not via passlib) for password hashing | Corrected during Code Generation 2026-08-01: passlib's bcrypt backend is incompatible with bcrypt>=4.0 (a known, unresolved upstream self-test bug); calling `bcrypt.hashpw`/`checkpw` directly avoids the unmaintained passlib shim entirely |
| API docs | Enabled at `/docs` (Swagger UI) and `/redoc` | Question 2 = A |
| Test framework | **pytest** + **httpx** (FastAPI's recommended async test client) | Matches Unit 1's test framework; httpx is the standard FastAPI testing companion |

## Package Dependency on Unit 1

Per `unit-of-work.md`, this unit installs the `database/` package (Unit 1) as a local editable dependency to reuse its SQLAlchemy models and migration helper, rather than duplicating schema definitions.
