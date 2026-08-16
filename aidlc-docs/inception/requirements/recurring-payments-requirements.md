# Requirements: Recurring Payments, Budget Alerts & Subscription Detection (Epic 8)

Tracked as a Post-Completion feature, same pattern as Epic 6 and Epic 7. Base project status unchanged: COMPLETE. This document is feature-scoped. **No real payee names, family details, or exact payment amounts appear anywhere in this document** — the user's real reference list was shared in chat only, and this repository is public; every example below is invented.

## Intent Analysis

- **User Request** (paraphrased, real figures omitted): the user maintains a personal, real list of recurring monthly and annual payments (loans, school fees, insurance, utilities, subscriptions, family obligations) to make sure funds are ready when each is due. They asked for budget alerts and subscription detection, prioritized as the next feature, and asked for a design that's intuitive.
- **Request Type**: New Feature
- **Scope Estimate**: Multiple Components — Database (new entities), Ingestion Worker Service (matching + detection logic), API Service (CRUD + status/alerts endpoints), Frontend SPA (new Dashboard section)
- **Complexity Estimate**: Complex — new domain entities, a two-phase trust/review matching workflow, a separate pattern-detection heuristic, and bulk import, combined into one feature.

## Requirements Depth
**Standard** — clarified via one round of 9 questions plus one targeted follow-up, all resolved with no remaining ambiguity.

## Functional Requirements

- **FR-1**: The system maintains a user-editable register of **Recurring Payments**, each with: a name, an expected amount (a loose guide, not exact — see FR-5), a frequency (`monthly` or `annual`), a due date (day-of-month for monthly; month + day for annual), and an optional link to an existing whitelist category.
- **FR-2**: A Recurring Payment can be added, edited, or removed one at a time via a form, matching the existing category-management UX pattern (Settings).
- **FR-3**: Recurring Payments can also be **bulk-imported** via a pasted or uploaded CSV (name, amount, frequency, due date), so an existing personal list can be loaded in one step rather than re-typed. The one-at-a-time form (FR-2) remains available for later edits.
- **FR-4**: This feature is presented as a new section/tab on the existing **Dashboard** page — not a separate top-level nav page.
- **FR-5**: When a new transaction is ingested, the system attempts to match it to an active Recurring Payment's current due cycle using description/category similarity (reusing the existing similarity-matching approach) plus the transaction's date falling within a due-date matching window. The Recurring Payment's expected amount is used only as a loose guide/sanity check — not an exact-match requirement (no fixed/variable payment type distinction is modeled).
- **FR-6**: The **first-ever** match found for a given Recurring Payment is always presented as a pending item for the user to approve or reject — it is never auto-applied, regardless of how close the amount is.
- **FR-7**: Once a Recurring Payment has had at least one match **approved**, it becomes **trusted**. For a trusted Recurring Payment, a later cycle's match auto-applies without review **only when** the matched transaction's amount is close to the expected amount (within a tolerance). If a trusted payment's match amount deviates beyond that tolerance, it still falls back to a pending review item rather than auto-applying.
- **FR-8**: Rejecting a pending match leaves the transaction untouched and does not change the Recurring Payment's trusted state — consistent with the existing recategorization-review reject behavior (Epic 6, FR-RR-8).
- **FR-9**: A Recurring Payment whose due date has passed with no matched transaction (pending, approved, or auto-applied) for the current cycle is marked **Overdue** immediately the day after the due date — no grace period.
- **FR-10**: A Recurring Payment approaching its due date, before it's due, is shown as **Due Soon** within a lead window.
- **FR-11**: Each **annual** Recurring Payment additionally displays a **monthly set-aside** figure (expected annual amount ÷ 12) alongside its due-date status, so the user can see what to be saving monthly to cover it.
- **FR-12 (Subscription Detection)**: The system periodically scans existing transaction history for repeating charges (similar description/category and amount, recurring on an approximately **monthly** cadence, appearing 2 or more times) that are **not yet** represented by any Recurring Payment, and surfaces them as suggestions the user can add to the register or dismiss. Annual-cadence pattern detection is explicitly out of scope for this version.
- **FR-13**: A dismissed detection suggestion does not reappear for the same underlying pattern.
- **FR-14**: The Dashboard's Recurring Payments section shows an in-app summary (counts of Due Soon / Overdue / Pending Review / new detection suggestions) with a badge/indicator, consistent with the existing Review page's pending-count badge pattern (Epic 6), so unresolved items are visible without opening the section. No email or other external notification channel in this version.

## Non-Functional Requirements

- **NFR-1**: Recurring-payment matching reuses the existing similarity-matching infrastructure (rapidfuzz-based, already used for transaction categorization) rather than introducing a new matching library or approach.
- **NFR-2**: Matching and detection processing fits within the existing Ingestion Worker Service architecture and its "no direct call to/from API Service" rule — coordination happens only through shared database rows, consistent with every prior feature in this project.
- **NFR-3**: Exact numeric values — the amount-closeness tolerance (FR-7), the due-date matching window (FR-5), the "Due Soon" lead time (FR-10), and the detection-pattern thresholds (FR-12) — are tuned during Functional/Code Generation, not hardcoded here, consistent with this project's established precedent (e.g. WR-3's `similarity_threshold`).
- **NFR-4**: Bulk CSV import (FR-3) validates each row independently and reports per-row errors without failing the entire import, consistent with this project's existing partial-failure-isolation pattern (e.g. NFR-2.2's per-file ingestion isolation, AR-11/AR-12's per-item bulk-action isolation).

## Business Context

- **Goal**: Give the user confidence that upcoming large or numerous recurring obligations won't be missed or under-funded, without manually tracking them outside the app; also surface recurring charges that were never explicitly registered.
- **Success Criteria**: The user's real recurring-payment list can be loaded in one step; the Dashboard clearly shows what's due soon, overdue, or waiting for review, without needing to check a separate spreadsheet; genuinely recurring but untracked charges get surfaced automatically instead of being noticed only by accident.

## Documented Assumptions (flagged, not further questioned)
1. The amount-closeness tolerance for FR-7's trusted auto-apply, the due-date matching window, and the "Due Soon" lead time are left as tunable defaults, set during Functional/Code Generation — not fixed here.
2. The bulk CSV import's exact column format/header requirements are a Functional/Code Generation detail.
3. No fixed/variable payment-type distinction is modeled (Q2 = A) — every Recurring Payment's expected amount is advisory only, used as a loose match signal.
4. Subscription detection considers only monthly-cadence patterns in this version (Q7 = A); annual-cadence detection is a natural future enhancement, not built now.
5. No email/external notification channel in this version (Q9 = A) — in-app badge/summary only.
6. This document intentionally omits the user's real payee names and payment amounts; all examples elsewhere in this feature's docs use invented placeholders.

## Out of Scope
- Fixed vs. variable payment-amount distinction (explicitly declined, Q2)
- Annual-cadence subscription auto-detection (deferred, Q7)
- Email/push notifications (deferred, Q9)
- A full audit-trail/undo editor beyond what the existing approve/reject review flow already provides
