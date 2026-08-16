# Code Generation Plan — API Service Unit — Recurring Payments (Epic 8)

**Unit**: API Service (Unit 2). **Stories**: US-8.1, US-8.2, US-8.3 (status), US-8.4, US-8.6, US-8.7 (status).
**Dependencies**: Database unit — complete.
**New module**: `api_service/recurring_payments/` (`cycle.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`).

## Steps

1. [x] **Errors**: `errors.py` +`InvalidRecurringPaymentError`, +`MatchNotPendingError`, +`DetectionSuggestionNotNewError`
2. [x] **Config**: `config.py` +`recurring_payment_due_soon_lead_days`
3. [x] **Cycle math**: `recurring_payments/cycle.py` — mirrors the Worker's due-date-instance functions plus 2 status-only additions (found necessary during implementation, see below)
4. [x] **Repository Layer**: `recurring_payments/repository.py`
5. [x] **Business Logic**: `recurring_payments/service.py`
6. [x] **Schemas**: `recurring_payments/schemas.py` — 11 DTOs
7. [x] **API Layer**: `recurring_payments/router.py` — 12 endpoints, auth-protected
8. [x] **Router registration**: `main.py`
9. [x] **Unit Testing**: `test_recurring_payments_cycle.py` (15), `test_recurring_payments_service.py` (27), `test_api_recurring_payments.py` (13)
10. [x] **Documentation**: `aidlc-docs/construction/api-service/code/recurring-payments-summary.md`

## Real Design Refinement Found During This Stage

- [x] The Functional Design's 3-state status model (`due_soon`/`overdue`/`paid`) couldn't correctly represent a pending-review cycle without misclassifying it. Refined to 4 states (`+ pending_review`) and replaced the originally-assumed "reuse the Worker's nearest-instance logic" with a purpose-built `latest_instance_on_or_before` + `next_instance_after` pair — documented in `business-rules.md`'s AR-15 with the exact algorithm and reasoning.

## Verification (not deferred to Build & Test — done now, live)

- [x] Full `api-service` unit test suite against a real disposable Postgres: 168/168 passing, zero regressions
- [x] OpenAPI schema smoke-tested: all 12 new routes present with the expected methods
