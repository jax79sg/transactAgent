# Business Logic + Repository Layer Summary — Unit 2: API Service

Covers Steps 2, 3, 5, 6, 7 of the code generation plan (business logic and repository layers are documented together since they're tightly coupled per domain area).

| Domain area | Service (business rules) | Repository (queries) | Tests |
|---|---|---|---|
| Auth | `auth/security.py` (hash/verify password, issue/decode JWT), `auth/dependencies.py` (AR-1) | — (no persisted entity beyond `User`, looked up in the router) | `test_auth_security.py` |
| Categories | `categories/service.py` (AR-3, AR-4, AR-5) | `categories/repository.py` | `test_categories_service.py` |
| Transactions | `transactions/service.py` (AR-2, AR-7, AR-9, AR-10, CSV export) | `transactions/repository.py` (filter/sort/group query builder — pure-function PBT candidate) | `test_transactions_service.py` |
| Dashboards | `dashboards/service.py` (AR-9) | `dashboards/repository.py` (3 aggregation queries + conversion disclosure) | `test_dashboards_service.py` |
| Ingestion | `ingestion/service.py` (AR-6) | `ingestion/repository.py` | `test_ingestion_service.py` |
| Recategorization Review | `recategorization/service.py` (AR-11, AR-12, AR-13) | `recategorization/repository.py` (joinedload-eager DTO queries, matching `transactions/repository.py`'s pattern) | `test_recategorization_service.py`, `test_api_recategorization.py` |

All 10 original API-layer business rules (AR-1 through AR-10) from `functional-design/business-rules.md` have at least one corresponding test with both a positive and negative case, except AR-1 and AR-8 which are exercised at the API layer (Step 10) rather than the service layer, since they're routing/pagination-clamping concerns rather than service-layer branching logic. AR-11/AR-12/AR-13 (added 2026-08-02, Epic 6) are covered at both the service layer (404/409/success + partial-bulk-failure) and the API layer (status codes, error-code shape, response body).

**Epic 6 notes**: `_get_pending_proposal()` is the one shared guard both `approve_proposal()` and `reject_proposal()` call through, so AR-11/AR-12 are enforced in exactly one place; `bulk_approve()`/`bulk_reject()` call the single-item functions per id and catch `NotFoundError`/`ProposalNotPendingError` to build the partial-failure response rather than duplicating the guard logic. Verified the FastAPI app's OpenAPI schema builds cleanly with all 6 new routes registered (`app.openapi()`), not just that unit tests pass, since router-registration/schema-generation bugs can slip past a unit-test-only check.
