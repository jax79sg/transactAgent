# Recurring Payments — Code Summary (Epic 8)

New module: [`api_service/recurring_payments/`](../../../../api-service/src/api_service/recurring_payments/).

| File | Purpose |
|---|---|
| `cycle.py` | Pure date-math — a **second, necessarily separate implementation** of the Worker's `cycle.py` (no shared library between the two services), plus 2 status-only additions: `latest_instance_on_or_before`, `next_instance_after` |
| `repository.py` | DB access for CRUD, match/suggestion queries and resolution writes |
| `service.py` | CRUD validation, bulk import (AR-19), status computation (AR-15/AR-16), approve/reject (AR-17/AR-18), dismiss/add (AR-20), status summary |
| `schemas.py` | 11 DTOs (CamelModel) |
| `router.py` | `/recurring-payments` — 12 endpoints, all auth-protected |

## Key implementation decisions

- **Status is a 4-state model, refined from 3 during Code Generation**: `due_soon` / `overdue` / `pending_review` / `paid`. A 3-state model (as originally specified in Functional Design) couldn't correctly represent "a pending match exists, so it's not overdue, but nothing is confirmed yet" — FR-9's own wording already implied this case existed. See `business-rules.md`'s AR-15 for the exact algorithm and the reasoning for the refinement.
- **Status algorithm found and fixed mid-implementation**: initially reused the Worker's `nearest_due_date_instance` (nearest instance to today) for status too, but that's the wrong rule here — it can jump straight to next month's due date and silently skip checking whether *last* month's bill was ever paid. Replaced with `latest_instance_on_or_before` (always the most recently due cycle) plus `next_instance_after` (to still show `due_soon` in advance of the next cycle once the current one is paid).
- **No write path for matching or detection**: this component only resolves what the Worker already proposed (approve/reject/dismiss/add) — matches every other review-style component in this project.

## Tests

- `tests/test_recurring_payments_cycle.py` (new): 15 tests, mirroring the Worker's cycle tests plus the 2 status-only functions
- `tests/test_recurring_payments_service.py` (new): 27 tests — CRUD validation, bulk import isolation, all 4 status outcomes, approve/reject + trust side effect, detection suggestion triage, status summary
- `tests/test_api_recurring_payments.py` (new): 13 tests — auth requirement, CRUD round trips, bulk import partial success, match review incl. 409 on double-resolve, detection suggestion list/dismiss/add

Full suite: 168/168 passing (up from 113). OpenAPI schema smoke-tested — all 12 routes registered as expected.
