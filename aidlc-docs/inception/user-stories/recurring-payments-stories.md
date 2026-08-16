# User Stories — Recurring Payments, Budget Alerts & Subscription Detection

Appends **Epic 8** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then + edge cases — matches the existing convention.
**Traceability**: Each story references `recurring-payments-requirements.md`'s FR/NFR IDs.
**Naming note**: examples in acceptance criteria below use invented placeholder payees (e.g. "Gym Membership," "Car Loan") — never the Account Owner's real, real-world list.

---

## Epic 8: Recurring Payments & Budget Alerts

### US-8.1: Build and maintain my recurring payments register
**As** the Account Owner, **I want** to add, edit, and remove recurring payments one at a time **so that** my list of expected bills stays accurate as things change.

**Traces to**: FR-1, FR-2

**Acceptance Criteria**:
- *Happy path*: Given I fill in a name, expected amount, frequency (monthly or annual), and due date, When I save, Then a new Recurring Payment appears in my register.
- *Happy path — category link*: Given I optionally pick one of my existing categories while adding a payment, When I save, Then the payment shows that category association wherever it's displayed.
- *Edge case — edit*: Given an existing Recurring Payment, When I change its amount or due date, Then future due/overdue calculations use the updated values, and past resolved matches are unaffected.
- *Edge case — remove*: Given a Recurring Payment I no longer need, When I remove it, Then it stops appearing in due/overdue/matching, without deleting any transactions it was ever matched to.

### US-8.2: Load my existing list in one step
**As** the Account Owner, **I want** to bulk-import my existing recurring-payments list (name, amount, frequency, due date) **so that** I don't have to re-type each one individually when I first set this up.

**Traces to**: FR-3, NFR-4

**Acceptance Criteria**:
- *Happy path*: Given a pasted or uploaded list of rows, When I import it, Then each valid row becomes its own Recurring Payment.
- *Edge case — partial failure*: Given some rows are malformed (missing a required field, an invalid frequency, or an unparseable date), When I import, Then the valid rows are still created and I see exactly which rows failed and why — the whole import doesn't abort because of a few bad rows.
- *Edge case — still editable after import*: Given payments created via bulk import, When I open one, Then I can edit or remove it exactly like a payment I added one at a time (US-8.1).

### US-8.3: See what's due, due soon, or overdue at a glance
**As** the Account Owner, **I want** my Dashboard to show which recurring payments are due soon, currently overdue, or paid **so that** I don't need a separate spreadsheet to know what's coming.

**Traces to**: FR-4, FR-9, FR-10, FR-11

**Acceptance Criteria**:
- *Happy path*: Given my recurring payments, When I open the Dashboard, Then a Recurring Payments section shows each one's status: Due Soon, Overdue, or Paid (this cycle), without leaving the page.
- *Happy path — annual set-aside*: Given an annual recurring payment, When I view it, Then I also see a monthly set-aside figure (its expected amount ÷ 12) alongside its due-date status.
- *Edge case — immediate overdue*: Given a monthly payment's due date passed yesterday with no matched transaction, When I view the Dashboard today, Then it shows Overdue (no grace period).
- *Edge case — no payments yet*: Given I haven't added any recurring payments, When I open the Dashboard, Then the section shows a clear empty state, not an error or a blank area.

### US-8.4: Review a proposed match before it counts
**As** the Account Owner, **I want** the first time a transaction is matched to one of my recurring payments to wait for my confirmation **so that** the app never silently assumes a match is correct before I've told it so.

**Traces to**: FR-5, FR-6, FR-8

**Acceptance Criteria**:
- *Happy path*: Given a new transaction resembles an unmatched, never-yet-approved recurring payment (similar description/category, within the due-date window), When ingestion processes it, Then it appears as a pending match for me to approve or reject — not auto-applied.
- *Happy path — approve*: Given a pending match, When I approve it, Then that recurring payment's current cycle is marked Paid, and the payment becomes "trusted" for future cycles (US-8.5).
- *Happy path — reject*: Given a pending match I don't agree with, When I reject it, Then the transaction is left completely untouched and the recurring payment's trusted state does not change.
- *Edge case — amount is only a guide*: Given a matched transaction's amount differs somewhat from the expected amount, When it's presented as a pending match, Then it's still shown for review (amount is a loose signal, not a strict filter) rather than being silently discarded.

### US-8.5: Let confirmed payments match themselves next time — mostly
**As** the Account Owner, **I want** a recurring payment I've already confirmed once to auto-match on its own next cycle **so that** I'm not stuck re-approving the same obvious payment every single month — but only when the amount still looks right.

**Traces to**: FR-7

**Acceptance Criteria**:
- *Happy path — auto-apply*: Given a recurring payment with at least one previously-approved match (trusted), When a new transaction matches it with an amount close to expected, Then that cycle is marked Paid automatically, with no review needed.
- *Edge case — amount drifts*: Given a trusted recurring payment, When a new matching transaction's amount deviates beyond the acceptable range, Then it does NOT auto-apply — it's presented as a pending match for review instead, exactly like a never-trusted payment would be.
- *Edge case — trust is per-payment*: Given one recurring payment is trusted, When a transaction matches a *different*, not-yet-approved recurring payment, Then that other payment still requires review (US-8.4) — trust never transfers between payments.

### US-8.6: Get told about recurring charges I never registered
**As** the Account Owner, **I want** the app to notice charges that keep recurring but aren't in my recurring-payments register **so that** I catch subscriptions or bills I forgot to track, without hunting through my transaction history myself.

**Traces to**: FR-12, FR-13

**Acceptance Criteria**:
- *Happy path*: Given a charge with a similar description/category and amount has occurred 2 or more times roughly a month apart, and no Recurring Payment already covers it, When the detection scan runs, Then it's surfaced as a suggestion I can add to my register or dismiss.
- *Happy path — add from suggestion*: Given a detection suggestion, When I add it, Then a new Recurring Payment is created pre-filled from the pattern (name/amount/frequency), which I can adjust before saving.
- *Edge case — dismiss is sticky*: Given I dismiss a suggestion, When the same underlying pattern is seen again later, Then it does not reappear as a new suggestion.
- *Edge case — annual patterns not attempted*: This story covers monthly-cadence detection only — a charge that recurs roughly yearly is not auto-detected in this version (explicitly out of scope, FR-12).

### US-8.7: See at a glance whether anything needs my attention
**As** the Account Owner, **I want** a single visible summary of everything needing a decision — overdue payments, pending matches, new detection suggestions — **so that** I know whether to check in without opening the Dashboard's recurring section every time.

**Traces to**: FR-14

**Acceptance Criteria**:
- *Happy path*: Given at least one overdue payment, pending match, or new detection suggestion exists, When I'm anywhere in the app, Then a badge/indicator (matching the existing Review pending-count badge pattern) shows there's something to look at.
- *Edge case — nothing pending*: Given nothing needs attention, When I look for the badge, Then it doesn't appear at all (no zero-count clutter) — matching the existing pending-count badge's own precedent.
- *Edge case — in-app only*: This story is satisfied entirely within the app itself — no email or other external notification is sent in this version (FR-14).
