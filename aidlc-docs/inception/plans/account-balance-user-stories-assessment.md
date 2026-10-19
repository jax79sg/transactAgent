# User Stories Assessment — Account Balance at a Point in Time

## Request Analysis
- **Original Request**: "I would like to add a new feature that is able to determine the balance of my accounts in a particular time."
- **User Impact**: Direct. New Dashboard section (lookup, chart, discrepancy warnings), a new account-management UI, a new anchor-entry flow, and a one-time backfill the user must consciously trigger and review.
- **Complexity Level**: Complex. All four units touched; new data model concepts (accounts, anchors); changed extraction contract; destructive backfill on live data.
- **Stakeholders**: Single end user (Account Owner persona, as in `personas.md`; single-user app).

## Assessment Criteria Met
- [x] High Priority: "New User Features: Any new functionality users will directly interact with". Balance lookup, balance chart, account management, and anchor entry are all new interactive functionality.
- [x] High Priority: "User Experience Changes: Modifications to existing user workflows or interfaces". The Dashboard gains a new section, and ingestion gains a new outcome the user must act on (new accounts to confirm, anchors to set).
- [x] High Priority: "Complex Business Logic: Requirements with multiple scenarios or business rules". Forward/backward computation from an anchor, a cross-check against statement closing balances, SGD conversion at an as-of date, and an exclusion rule for non-deposit accounts.
- [x] Medium Priority factors also apply: scope spans multiple components, and risk is high (destructive backfill), so a testable statement of the safe-backfill experience has real value.
- [x] Benefits: Concrete acceptance criteria for the states the requirements leave implicit (account without an anchor, a discrepancy warning, a date after the latest ingested transaction, a foreign-currency account with no FX rate, an unmatched manual correction after reingest).

## Decision
**Execute User Stories**: Yes
**Reasoning**: Meets three High Priority criteria directly and matches this project's consistent precedent: every user-facing feature (Recategorization Review, Nightly Backup, Recurring Payments, Configurable App Settings, Background Process Visibility, Dark Mode) executed User Stories; only backend-only, algorithm, or tooling changes skipped it. The "Add User Stories" opt-out was not offered at Requirements Analysis for this reason.

## Expected Outcomes
- Testable acceptance criteria for every user-visible state and failure mode, including the ones that protect the user from misreading a balance (no-anchor, stale-data, excluded-from-total, discrepancy).
- A story for the backfill that makes its safety gates (backup, dry-run report, explicit confirmation, unmatched-correction report) testable rather than implicit.
- Reuses the existing single-persona model; no new persona work needed.
