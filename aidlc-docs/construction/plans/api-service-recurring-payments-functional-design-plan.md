# Functional Design Plan — API Service Unit — Recurring Payments (Epic 8)

**Unit**: API Service (Unit 2). **Scope**: the Recurring Payments Component — CRUD, bulk import, match review, detection-suggestion triage, and the Due Soon/Overdue status computation deferred here from the Ingestion Worker's Functional Design.

## No blocking questions

Everything needed follows from Requirements (FR-1..14), Application Design's method signatures, and the Ingestion Worker's explicit deferral of status computation to this unit. One thing worth stating explicitly: the Due Soon/Overdue/Paid classification (AR-15) is **read-time, not stored** — computed fresh on every request from `RecurringPayment.due_day`/`due_month`, today's date, and whether a live/resolved match exists for the current cycle. This matches how Dashboard/Insights already computes aggregates on read rather than persisting derived state.

## Execution Checklist

- [ ] Add AR-15..20 to `business-rules.md`:
  - AR-15: Due Soon/Overdue/Paid status computation (read-time, no grace period per FR-9)
  - AR-16: annual monthly set-aside figure in the status response
  - AR-17: a match must exist and be pending to approve/reject (mirrors AR-11/12)
  - AR-18: approving writes through (marks cycle Paid) and sets `is_trusted` on the payment; rejecting has no side effects beyond the match's own status (FR-8)
  - AR-19: bulk import validates each row independently, partial success (NFR-4)
  - AR-20: dismiss sets a suggestion `dismissed` (permanent, BR-22); add-from-suggestion creates a pre-filled `RecurringPayment` and marks the suggestion `added`
- [ ] Add `RecurringPaymentDTO`, `RecurringPaymentMatchDTO`, `DetectionSuggestionDTO`, `RecurringPaymentsStatusSummaryDTO`, bulk-import request/response DTOs to `domain-entities.md`
- [ ] Add a **Recurring Payments Component** section to `business-logic-model.md` describing CRUD, bulk import row validation, the status-computation algorithm, and approve/reject/dismiss/add logic
- [ ] New router: `/recurring-payments` (CRUD, `/bulk-import`, `/matches`, `/matches/{id}/approve`, `/matches/{id}/reject`, `/detection-suggestions`, `/detection-suggestions/{id}/dismiss`, `/detection-suggestions/{id}/add`, `/status`), registered in `main.py`
