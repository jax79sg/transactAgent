# Functional Design Plan — Ingestion Worker Service Unit — Recurring Payments (Epic 8)

**Unit**: Ingestion Worker Service (Unit 3). **Scope**: new **Recurring Payment Manager Component** (`matchNewTransaction`, `isDetectionScanDueNow`, `runDetectionScan`), reusing the Categorization Engine's similarity matcher (no new component there).

## No blocking questions, but one genuine design gap worth resolving explicitly

Everything in FR-5..13 is well-specified, except one nuance neither Requirements nor Application Design pinned down: **which calendar cycle does a match belong to** when the matching window spans a month/year boundary? A monthly payment due on the 1st with a ±N-day window could catch a transaction from the *previous* month's tail end — is that the previous cycle's match (arriving a few days early) or this cycle's (arriving very early)?

**Resolution**: the due-date *instance* considered is whichever of "this payment's due date in the transaction's month" or "in the adjacent month" is numerically closer (by day distance) to the transaction's actual date. `cycle_period` is derived from that chosen instance's month/year (or year alone for annual), not from the transaction's own calendar month. This is deterministic, has no genuine product tradeoff, and is exactly the kind of edge case this project's precedent (e.g. WR-6's currency-source priority ordering) resolves as a technical design call rather than a question.

## Execution Checklist

- [ ] Add WR-16..19 to `business-rules.md`:
  - WR-16: matching trigger (hooked into `_persist_transaction`) + candidate selection (unresolved-this-cycle, similarity + due-date window, amount as loose guide)
  - WR-17: cycle-period derivation (the nearest-due-date-instance resolution above)
  - WR-18: trust/tolerance auto-apply decision, reusing the existing dual-gate amount-tolerance pattern already established for similarity matching (percentage tolerance OR an absolute floor, exact values tuned at Code Generation — same precedent as WR-3)
  - WR-19: detection scan cadence + pattern criteria (monthly-cadence only, ≥2 occurrences, exact thresholds tuned at Code Generation)
- [ ] Add a **Recurring Payment Manager Component** section to `business-logic-model.md` with `matchNewTransaction()`/`runDetectionScan()` pseudocode, matching the style of the Backup Manager section
- [ ] Add a **Categorization Engine** addendum noting its similarity matcher gains a second caller (already noted in Application Design; Functional Design confirms no internal logic changes)
- [ ] Add an addendum to `domain-entities.md` — no new internal DTO needed beyond what Unit 1's schema already provides, matching precedent

## Explicitly Deferred to API Service's Functional Design

Due Soon / Overdue status (FR-9/FR-10) is a **derived, read-time** computation (today's date vs. a payment's due day/month, and whether a resolved match exists for the current cycle) — it belongs to the API Service's Recurring Payments Component, matching how Dashboard/Insights already computes aggregates on read rather than the Worker writing a status column. Not a Worker responsibility; not covered by WR-16..19.
