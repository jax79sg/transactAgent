# Code Generation Plan — API Service Unit — Recategorization Review Panel

**Unit**: API Service (Unit 2). **Stories**: US-6.4, US-6.5, US-6.6.
**Dependencies**: Database unit (complete).

## Steps

1. [x] **Business Logic Generation**:
   - Created: `api-service/src/api_service/recategorization/{__init__.py, schemas.py, service.py, repository.py, router.py}`
   - Modified: `api-service/src/api_service/errors.py` — `ProposalNotPendingError` (AR-12)
   - Modified: `api-service/src/api_service/main.py` — registered the new router
2. [x] **API Layer Generation**: 6 endpoints under `/recategorization` (list, pending-count, approve, reject, bulk-approve, bulk-reject), all JWT-protected, matching the existing `ingestion/router.py` pattern
3. [x] **Repository Layer Generation**: `find_by_id`, `list_pending`, `count_pending`, all using `joinedload` matching `transactions/repository.py`'s convention (candidate transaction + its category, proposed category, triggering job all eager-loaded to avoid N+1 in the list endpoint)
4. [x] **Business/API Layer Unit Testing**:
   - Created: `api-service/tests/test_recategorization_service.py` (11 tests — list/count/approve/reject/bulk, including partial-bulk-failure)
   - Created: `api-service/tests/test_api_recategorization.py` (9 tests — same coverage through the HTTP layer, plus auth-required and status-code/error-shape checks)
5. [x] **Documentation Generation**:
   - Modified: `aidlc-docs/construction/api-service/code/api-layer-summary.md`, `business-logic-summary.md`

## Verification

- [x] Ran the two new test files in isolation: 18/18 passing
- [x] Ran the full `api-service` unit test suite: 87/87 passing, no regressions
- [x] Smoke-tested `create_app(run_migrations=False).openapi()` directly — confirmed the schema builds cleanly and all 6 new routes are registered, since a router-registration or schema-generation bug wouldn't necessarily show up in endpoint-level tests alone
