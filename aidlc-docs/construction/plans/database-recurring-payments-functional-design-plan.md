# Functional Design Plan — Database Unit — Recurring Payments (Epic 8)

**Unit**: Database (Unit 1). **Scope**: three new entities — `RecurringPayment` (the register), `RecurringPaymentMatch` (per-cycle match/review record), `DetectionSuggestion` (untracked-pattern suggestions).

## No blocking questions

Shapes follow directly from Requirements (FR-1..14) and Application Design's method signatures. Two structural choices worth stating explicitly (technical calls, not product questions):

1. **`RecurringPaymentMatch` needs a real `pending`/`approved`/`rejected`/`auto_applied` state machine** (unlike `BackupRun`'s write-once design) — because, exactly like `RecategorizationProposal`, a match genuinely is created in one state and can transition later via a separate user action (approve/reject). It's structurally the closest sibling to `RecategorizationProposal` in this schema, so it reuses that same shape (a `cycle_period` identifier standing in for what `recategorization_job_id` groups there).
2. **Sticky dismissal (FR-13) is a `UNIQUE` constraint, not app logic**: `DetectionSuggestion.description_pattern` is unique — one row ever exists per pattern, and its `status` transitions (`new` → `dismissed` or `added`) rather than new rows being inserted on every re-scan. A re-scan that finds an existing row for a pattern simply skips creating a duplicate, which is what makes "dismissed never reappears" free at the schema level rather than something the Worker has to remember separately.

## Execution Checklist

- [ ] Add `RecurringPayment`, `RecurringPaymentMatch`, `DetectionSuggestion` entities to `domain-entities.md` + ER diagram edges
- [ ] Add business rules to `business-rules.md` (starting BR-19):
  - Annual payments require a due month, monthly payments must not have one (CHECK)
  - Due day is 1–31 (CHECK)
  - At most one "live" (non-rejected) match per recurring payment per cycle (partial unique index, same pattern as BR-10/BR-14)
  - Detection pattern uniqueness (plain unique constraint — the FR-13 enforcement mechanism)
  - A match resolves out of `pending` exactly once (app-layer, same pattern as BR-16)
- [ ] Add to `business-logic-model.md`: `RecurringPaymentMatch.status` lifecycle (mirrors `RecategorizationProposal`'s diagram) and `RecurringPayment.is_trusted`'s one-way false→true transition
